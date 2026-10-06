import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from sukoon.models import (
    CHECKSUM_MESSAGE,
    MODEL_FILES,
    PRIMARY,
    ModelChecksumError,
    ModelFile,
    Preset,
    sha256_of,
)

OFFLINE_MESSAGE = "Couldn't download the model. Check your connection, then retry."

# done bytes, total bytes, bytes per second
Progress = Callable[[int, int, float], None]


class DownloadError(Exception):
    pass


def _fetch(f: ModelFile, part: Path, timeout: float, on_chunk: Callable[[int], None]) -> None:
    if not f.url.startswith(("https://", "http://127.0.0.1:")):
        raise ValueError(f"refusing to fetch {f.url}")
    have = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(f.url, headers={"user-agent": "sukoon"})  # noqa: S310
    if have:
        request.add_header("range", f"bytes={have}-")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - pinned URL
        # A server that ignores Range sends the whole file again.
        mode = "ab" if have and response.status == 206 else "wb"
        with part.open(mode) as out:
            while block := response.read(1 << 16):
                out.write(block)
                on_chunk(len(block))


def download_file(
    f: ModelFile, models_dir: Path, on_progress: Progress, timeout: float = 30, attempts: int = 4
) -> Path:
    """Streams to a .part file, resumes after drops, and renames only once the hash matches."""
    target = models_dir / f.name
    part = models_dir / f"{f.name}.part"
    models_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    fresh = 0

    def on_chunk(n: int) -> None:
        nonlocal fresh
        fresh += n
        done = part.stat().st_size if part.exists() else 0
        on_progress(done, f.size, fresh / max(time.monotonic() - started, 1e-6))

    for attempt in range(attempts):
        try:
            _fetch(f, part, timeout, on_chunk)
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            if attempt == attempts - 1:
                raise DownloadError(OFFLINE_MESSAGE) from exc
        # A connection closed early can end the body without an error, so the size decides.
        if part.exists() and part.stat().st_size >= f.size:
            break
        if attempt == attempts - 1:
            raise DownloadError(OFFLINE_MESSAGE)
        time.sleep(min(2**attempt, 8))
    if part.stat().st_size != f.size or sha256_of(part) != f.sha256:
        part.unlink(missing_ok=True)
        raise ModelChecksumError(CHECKSUM_MESSAGE)
    part.replace(target)
    return target


def download_preset(
    models_dir: Path,
    preset: Preset,
    on_progress: Progress,
    files: tuple[ModelFile, ...] = MODEL_FILES,
) -> None:
    """Fetches every missing file of a preset; progress is reported for the preset as a whole."""
    wanted = [f for f in files if f.preset == preset]
    total = sum(f.size for f in wanted)
    offset = 0
    for f in wanted:
        target = models_dir / f.name
        if not (target.is_file() and target.stat().st_size == f.size):
            base = offset

            def overall(done: int, _total: int, rate: float, base: int = base) -> None:
                on_progress(base + done, total, rate)

            download_file(f, models_dir, overall)
        offset += f.size
        on_progress(offset, total, 0.0)
    fetch_separator_metadata(models_dir, PRIMARY[preset])


def fetch_separator_metadata(models_dir: Path, model_name: str) -> None:
    """audio-separator reads small JSON tables of model settings that it fetches for itself.

    The pinned model file is already in place, so only those tables are downloaded.
    """
    try:
        from audio_separator.separator import Separator
    except ImportError:
        return
    separator = Separator(
        model_file_dir=str(models_dir), output_dir=str(models_dir), info_only=True
    )
    separator.download_model_files(model_name)
