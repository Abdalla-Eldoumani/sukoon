"""Links people paste: which sites are accepted, and fetching one into a job's folder."""

import copy
import ipaddress
import multiprocessing as mp
import os
import queue
import shutil
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sukoon import ffmpeg
from sukoon.errors import Canceled, JobError
from sukoon.probe import Rejected, inspect

# Each accepted site, and the yt-dlp extractor family allowed to read it.
SITES = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "x.com": "twitter",
    "twitter.com": "twitter",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "reddit.com": "reddit",
    "v.redd.it": "reddit",
    "vimeo.com": "vimeo",
    "soundcloud.com": "soundcloud",
}
NAMES = {
    "youtube": "YouTube",
    "twitter": "X",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "reddit": "Reddit",
    "vimeo": "Vimeo",
    "soundcloud": "SoundCloud",
}
# No yt-dlp reader handles these short links; they redirect to one that does.
SHORT = {"fb.watch", "v.redd.it"}

UPDATE = "uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync"
REFUSED = (
    "sukoon takes links from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and "
    "SoundCloud. For anything else, download the file and drop it here."
)
PLAYLIST = "This link is a playlist or a channel. Paste the link of one video."
LIVE = "This is a live stream. Paste the link again once it has ended."
DRM = "This video is protected against copying (DRM), so it can't be fetched."
PRIVATE = "This video is private or was deleted, so it can't be fetched."
AGE = "This video is age-restricted, and sukoon never signs in, so it can't be fetched."
REGION = "This video isn't available in your region."
LOGIN = (
    "{name} only shares this video with signed-in people, and sukoon never signs in. "
    "Save it another way and drop the file here."
)
ELSEWHERE = "This post points to a video on another site. Open it there and paste that link."
NETWORK = "The connection dropped while fetching. Check your connection, then retry."
OUTDATED = (
    "yt-dlp couldn't read this {name} page. Its reader may be out of date, or {name} turned "
    "the request away. To update it, run: " + UPDATE
)
STALLED = "The download made no progress for 10 minutes, so it was stopped."
CRASHED = "The download stopped unexpectedly."
STREAM = "This video is only offered as a kind of stream sukoon doesn't fetch."

# What a link becomes: H.264 and AAC up to 1080p where offered, so MP4 copies it as it is.
# Video and audio come as separate parts, never merged by yt-dlp; sukoon checks and joins them.
FORMAT = (
    "bv[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/bv[height<=1080]+ba/bv+ba/b[height<=1080]/b/ba"
)
# Protocols yt-dlp downloads itself; anything else would hand the stream to another program.
PROTOCOLS = {"https", "http", "m3u8", "m3u8_native", "http_dash_segments"}
STALLED_S = 600.0
PROGRESS_EVERY_S = 0.25


class LinkRefused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def site(url: str) -> str:
    """The accepted site a link belongs to (youtube.com for www.youtube.com); raises LinkRefused.

    Only plain https links to the listed hosts or their subdomains: no user part, no port, no
    raw addresses, no look-alike letters.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise LinkRefused(REFUSED) from None
    host = parts.hostname or ""
    if parts.scheme != "https" or parts.username is not None or port is not None:
        raise LinkRefused(REFUSED)
    if not host.isascii() or _is_address(host):
        raise LinkRefused(REFUSED)
    for name in SITES:
        if host == name or host.endswith(f".{name}"):
            return name
    raise LinkRefused(REFUSED)


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


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
        return f"This video is longer than {max_seconds / 3600:g} hours, which is sukoon's limit."
    if sum(expected_size(p, seconds) for p in parts) > max_bytes:
        gb = max_bytes / 1024**3
        return f"This video is bigger than {gb:g} GB, which is sukoon's limit."
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
    if has("please report this issue", "unable to extract", "nsig", "signature", "challenge"):
        return OUTDATED.format(name=name)
    if has("unexpected response"):
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


def _resolve_short(url: str) -> str:
    """Follows a short link to the page it stands for, refusing any hop off the accepted sites."""

    class StayOnSite(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> Any:
            site(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(StayOnSite)
    request = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})  # noqa: S310
    with opener.open(request, timeout=30) as response:
        final: str = response.geturl()
    site(final)
    return final


def download(
    url: str, folder: Path, report: Callable[[str, Any], None], max_seconds: float, max_bytes: int
) -> list[Path]:
    """Runs yt-dlp: metadata and refusals first, then each part on its own. Child process only."""
    # yt-dlp would otherwise import plugin code from the user's folders.
    os.environ["YTDLP_NO_PLUGINS"] = "1"
    import yt_dlp
    from yt_dlp.utils import DownloadError, GeoRestrictedError

    family = SITES[site(url)]
    node = shutil.which("node")
    options: dict[str, Any] = {
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
    try:
        if site(url) in SHORT:
            url = _resolve_short(url)
        with yt_dlp.YoutubeDL(options) as ydl:
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
            with yt_dlp.YoutubeDL(one) as ydl:
                ydl.process_ie_result(copy.deepcopy(raw), download=True)
    except LinkRefused as exc:
        raise JobError(exc.message) from None
    except DownloadError as exc:
        cause = exc.exc_info[1] if exc.exc_info else None
        raise JobError(explain(str(exc), family, isinstance(cause, GeoRestrictedError))) from None
    return sorted(p for p in folder.glob("part*") if not p.name.endswith((".part", ".ytdl")))


def fetch_main(url: str, folder: str, outbox: Any, max_seconds: float, max_bytes: int) -> None:
    """The child process: downloads into `folder` and reports through `outbox`."""
    from sukoon.worker import exit_with_parent

    threading.Thread(target=exit_with_parent, daemon=True).start()
    try:
        parts = download(url, Path(folder), lambda *m: outbox.put(m), max_seconds, max_bytes)
        outbox.put(("done", [str(p) for p in parts]))
    except JobError as exc:
        outbox.put(("error", str(exc)))
    except Exception as exc:
        outbox.put(("error", explain(str(exc), SITES.get(_site_or(url), ""))))


def _site_or(url: str) -> str:
    try:
        return site(url)
    except LinkRefused:
        return ""


@dataclass
class Fetched:
    title: str
    parts: list[Path]


Target = Callable[[str, str, Any, float, int], None]


def fetch(
    url: str,
    folder: Path,
    on_progress: Callable[[int, int | None], None],
    cancelled: Callable[[], bool],
    max_seconds: float,
    max_bytes: int,
    target: Target = fetch_main,
    stall_s: float = STALLED_S,
) -> Fetched:
    """Downloads a link in a child process, so a hang or crash in yt-dlp can't reach the server.

    Cancelling kills the child; so does ten minutes without a word from it. Raises JobError
    with a sentence for the user, or Canceled.
    """
    folder.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    outbox: Any = ctx.Queue()
    child = ctx.Process(
        target=target,
        args=(url, str(folder), outbox, max_seconds, max_bytes),
        daemon=True,
        name="sukoon-fetch",
    )
    child.start()
    title = ""
    heard = time.monotonic()
    try:
        while True:
            if cancelled():
                raise Canceled
            try:
                message = outbox.get(timeout=0.2)
            except queue.Empty:
                if not child.is_alive() and outbox.empty():
                    raise JobError(CRASHED) from None
                if time.monotonic() - heard > stall_s:
                    raise JobError(STALLED) from None
                continue
            heard = time.monotonic()
            kind = message[0]
            if kind == "title":
                title = message[1]
            elif kind == "progress":
                on_progress(*message[1])
            elif kind == "done":
                return Fetched(title, [Path(p) for p in message[1]])
            else:
                raise JobError(message[1])
    finally:
        if child.is_alive():
            child.kill()
        child.join(timeout=5)


def assemble(folder: Path, parts: list[Path], cancelled: Callable[[], bool]) -> Path:
    """Checks each downloaded part as an upload is checked, then joins picture and sound into
    one source file with sukoon's own ffmpeg, so nothing that fails a check is ever opened."""
    if not parts:
        raise JobError(CRASHED)
    try:
        probes = [inspect(p) for p in parts]
    except Rejected as exc:
        raise JobError(exc.message) from None
    if len(parts) == 1:
        source = folder / f"source{parts[0].suffix.lower()}"
        parts[0].replace(source)
        return source
    video = next((p for p, r in zip(parts, probes, strict=True) if r.video), parts[0])
    audio = next((p for p, r in zip(parts, probes, strict=True) if r.audio), parts[-1])
    mp4 = all(p.suffix.lower() in (".mp4", ".m4a") for p in (video, audio))
    source = folder / ("source.mp4" if mp4 else "source.mkv")
    ffmpeg.run(
        [
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(video),
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-f",
            "mp4" if mp4 else "matroska",
            "-y",
            str(source),
        ],
        max(r.duration for r in probes),
        cancelled=cancelled,
    )
    for part in parts:
        part.unlink(missing_ok=True)
    return source
