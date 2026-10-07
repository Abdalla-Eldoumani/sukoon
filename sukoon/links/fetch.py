"""Fetching a link into a job's folder from the server's side: a child process does the download,
and its parts are checked like an upload before sukoon joins them."""

import multiprocessing as mp
import queue
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sukoon.errors import Canceled, JobError
from sukoon.links.messages import CRASHED, STALLED, too_big
from sukoon.links.ytdlp import fetch_main
from sukoon.media import ffmpeg
from sukoon.media.probe import MEDIA_EXTS, Rejected, inspect

STALLED_S = 600.0


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
                # The title becomes a file name, where a trailing dot or space would double up.
                title = message[1].rstrip(". ") or "video"
            elif kind == "progress":
                # A site can leave out the size until the bytes arrive, so the limit holds here too.
                if message[1][0] > max_bytes:
                    raise JobError(too_big(max_bytes))
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
        suffix = parts[0].suffix.lower()
        source = folder / f"source{suffix if suffix in MEDIA_EXTS else ''}"
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
