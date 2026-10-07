import http.client
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from sukoon.separation.models import (
    CHECKSUM_MESSAGE,
    MODEL_FILES,
    ModelChecksumError,
    ModelFile,
    Preset,
    is_ready,
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


class Downloads:
    """Model downloads started from the interface, one thread per preset, with live state."""

    def __init__(
        self,
        models_dir: Path,
        on_change: Callable[[dict[str, object]], None],
        on_ready: Callable[[], None],
        files: tuple[ModelFile, ...] = MODEL_FILES,
    ) -> None:
        self.models_dir = models_dir
        self.on_change = on_change
        self.on_ready = on_ready
        self.files = files
        self.lock = threading.Lock()
        self.active: dict[str, dict[str, object]] = {}

    def state(self, preset: Preset) -> dict[str, object]:
        total = sum(f.size for f in self.files if f.preset == preset)
        ready = is_ready(self.models_dir, preset, self.files)
        base: dict[str, object] = {
            "preset": preset,
            "ready": ready,
            "size": total,
            "downloading": False,
            "done": total if ready else 0,
            "rate": 0.0,
            "error": None,
        }
        with self.lock:
            return {**base, **self.active.get(preset, {})}

    def start(self, preset: Preset) -> None:
        with self.lock:
            if self.active.get(preset, {}).get("downloading"):
                return
            self.active[preset] = {"downloading": True, "done": 0, "rate": 0.0, "error": None}
        threading.Thread(
            target=self._run, args=(preset,), daemon=True, name=f"sukoon-download-{preset}"
        ).start()

    def _set(self, preset: Preset, **fields: object) -> None:
        with self.lock:
            self.active[preset] = {**self.active.get(preset, {}), **fields}
        self.on_change(self.state(preset))

    def _run(self, preset: Preset) -> None:
        last = 0.0

        def progress(done: int, total: int, rate: float) -> None:
            nonlocal last
            now = time.monotonic()
            if now - last >= 0.25 or done == total:
                last = now
                self._set(preset, done=done, rate=rate)

        try:
            download_preset(self.models_dir, preset, progress, self.files)
        except ModelChecksumError as exc:
            self._set(preset, downloading=False, error=str(exc))
            return
        except Exception:
            self._set(preset, downloading=False, error=OFFLINE_MESSAGE)
            return
        with self.lock:
            self.active.pop(preset, None)
        self.on_change(self.state(preset))
        self.on_ready()
