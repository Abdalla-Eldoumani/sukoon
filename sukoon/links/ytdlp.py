"""yt-dlp, locked down. Everything here runs in the fetch's child process, never in the server."""

import copy
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sukoon.errors import JobError
from sukoon.links.messages import (
    AGE,
    DRM,
    ELSEWHERE,
    LIVE,
    LOGIN,
    NETWORK,
    OUTDATED,
    PLAYLIST,
    PRIVATE,
    REGION,
    STREAM,
    TURNED_AWAY,
    too_big,
    too_long,
)
from sukoon.links.sites import NAMES, SHORT, SITES, LinkRefused, resolve_short, site, site_or_blank

# What a link becomes: H.264 and AAC up to 1080p where offered, so MP4 copies it as it is.
# Video and audio come as separate parts, never merged by yt-dlp; sukoon checks and joins them.
FORMAT = (
    "bv[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/bv[height<=1080]+ba/bv+ba/b[height<=1080]/b/ba"
)
# Protocols yt-dlp downloads itself; anything else would hand the stream to another program.
PROTOCOLS = {"https", "http", "m3u8", "m3u8_native", "http_dash_segments"}
PROGRESS_EVERY_S = 0.25


def expected_size(part: dict[str, Any], seconds: float) -> float:
    size = part.get("filesize") or part.get("filesize_approx")
    if size:
        return float(size)
    # Kilobits per second over the whole duration.
    return float(part.get("tbr") or 0) * 125 * seconds


def refusal(info: dict[str, Any], max_seconds: float, max_bytes: int) -> str | None:
    """Why a link's metadata rules it out before anything is downloaded, if it does."""
    if info.get("_type") in ("playlist", "multi_video"):
        return PLAYLIST
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        return LIVE
    parts = info.get("requested_formats") or [info]
    if any(p.get("has_drm") for p in parts):
        return DRM
    if any(p.get("protocol") and p["protocol"] not in PROTOCOLS for p in parts):
        return STREAM
    seconds = float(info.get("duration") or 0)
    if seconds > max_seconds:
        return too_long(max_seconds)
    if sum(expected_size(p, seconds) for p in parts) > max_bytes:
        return too_big(max_bytes)
    return None


def explain(message: str, family: str, geo: bool = False) -> str:
    """A sentence for a yt-dlp error: what happened and what to do."""
    text = message.lower()
    name = NAMES.get(family, "this site")

    def has(*words: str) -> bool:
        return any(w in text for w in words)

    if geo or has("available in your country", "geo restrict", "from your location"):
        return REGION
    if has("confirm your age", "age-restricted", "age restricted", "inappropriate for some"):
        return AGE
    if has("private video", "video is private", "video unavailable", "video is unavailable"):
        return PRIVATE
    if has("has been removed", "no longer available", "does not exist", "http error 404"):
        return PRIVATE
    if has("--cookies", "logged-in", "log in", "login", "sign in", "registered users"):
        return LOGIN.format(name=name)
    if has("http error 401", "http error 403"):
        return LOGIN.format(name=name)
    if has("live event", "is live", "premieres in"):
        return LIVE
    if has("drm"):
        return DRM
    if has("no suitable extractor", "unsupported url"):
        return ELSEWHERE
    if has("timed out", "getaddrinfo", "name resolution", "unreachable", "connection", "ssl"):
        return NETWORK
    # The site answered with something other than its page; a newer yt-dlp reads it no better.
    if has("unexpected response"):
        return TURNED_AWAY.format(name=name)
    if has("please report this issue", "unable to extract", "nsig", "signature", "challenge"):
        return OUTDATED.format(name=name)
    detail = message.removeprefix("ERROR: ").split(": ", 1)[-1].strip()
    return f"Couldn't fetch this video. yt-dlp said: {detail}"


class _Quiet:
    """yt-dlp's logger: errors come back as exceptions, so nothing is printed."""

    def debug(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def ytdl_options(family: str, folder: Path) -> dict[str, Any]:
    node = shutil.which("node")
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _Quiet(),
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "cachedir": False,
        "js_runtimes": {"node": {"path": node} if node else {}},
        "remote_components": [],
        "external_downloader": {"default": "native"},
        "fixup": "never",
        "postprocessors": [],
        "allowed_extractors": [f"{family}.*"],
        "paths": {"home": str(folder), "temp": str(folder)},
        # No ffmpeg for yt-dlp: it would otherwise take over some streams and fetch whatever
        # they point at. sukoon joins the parts itself.
        "ffmpeg_location": str(folder / "no-ffmpeg"),
        "socket_timeout": 30,
        "overwrites": True,
        "format": FORMAT,
    }


def guarded(options: dict[str, Any]) -> Any:
    """A YoutubeDL that reads no address off the list. A post can hand yt-dlp a link elsewhere
    (an X card's t.co link), and yt-dlp would request it before finding no extractor for it."""
    import yt_dlp

    class Guarded(yt_dlp.YoutubeDL):  # type: ignore[misc]
        def extract_info(self, url: str, *args: Any, **kwargs: Any) -> Any:
            # A bare video id passed on with its extractor's name has no address to check.
            if "://" in url:
                try:
                    site(url)
                except LinkRefused:
                    raise LinkRefused(ELSEWHERE) from None
            return super().extract_info(url, *args, **kwargs)

    return Guarded(options)


def download(
    url: str, folder: Path, report: Callable[[str, Any], None], max_seconds: float, max_bytes: int
) -> list[Path]:
    """Runs yt-dlp: metadata and refusals first, then each part on its own."""
    # yt-dlp would otherwise import plugin code from the user's folders.
    os.environ["YTDLP_NO_PLUGINS"] = "1"
    from yt_dlp.utils import DownloadError, GeoRestrictedError

    family = SITES[site(url)]
    options = ytdl_options(family, folder)
    try:
        if site(url) in SHORT:
            url = resolve_short(url)
        with guarded(options) as ydl:
            raw = ydl.extract_info(url, download=False, process=False)
            if reason := refusal(raw, max_seconds, max_bytes):
                raise JobError(reason)
            info = ydl.process_ie_result(copy.deepcopy(raw), download=False)
        if reason := refusal(info, max_seconds, max_bytes):
            raise JobError(reason)
        report("title", str(info.get("title") or info.get("id") or "video"))
        parts = info.get("requested_formats") or [info]
        seconds = float(info.get("duration") or 0)
        sizes = [expected_size(p, seconds) for p in parts]
        last = 0.0
        for index, part in enumerate(parts):

            def hook(d: dict[str, Any], index: int = index) -> None:
                nonlocal last
                if d.get("status") != "downloading":
                    return
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                sizes[index] = float(total or sizes[index])
                done = sum(sizes[:index]) + float(d.get("downloaded_bytes") or 0)
                now = time.monotonic()
                if now - last >= PROGRESS_EVERY_S:
                    last = now
                    report("progress", (int(done), int(sum(sizes)) or None))

            one = {
                **options,
                "format": part["format_id"],
                "outtmpl": {"default": f"part{index}.%(ext)s"},
                "progress_hooks": [hook],
            }
            with guarded(one) as ydl:
                ydl.process_ie_result(copy.deepcopy(raw), download=True)
    except LinkRefused as exc:
        raise JobError(exc.message) from None
    except DownloadError as exc:
        cause = exc.exc_info[1] if exc.exc_info else None
        raise JobError(explain(str(exc), family, isinstance(cause, GeoRestrictedError))) from None
    return sorted(p for p in folder.glob("part*") if not p.name.endswith((".part", ".ytdl")))


def fetch_main(url: str, folder: str, outbox: Any, max_seconds: float, max_bytes: int) -> None:
    """The child process: downloads into `folder` and reports through `outbox`."""
    from sukoon.separation.worker import exit_with_parent

    threading.Thread(target=exit_with_parent, daemon=True).start()
    try:
        parts = download(url, Path(folder), lambda *m: outbox.put(m), max_seconds, max_bytes)
        outbox.put(("done", [str(p) for p in parts]))
    except JobError as exc:
        outbox.put(("error", str(exc)))
    except Exception as exc:
        outbox.put(("error", explain(str(exc), SITES.get(site_or_blank(url), ""))))
