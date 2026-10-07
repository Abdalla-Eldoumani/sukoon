import errno
import subprocess
import threading
import time
from collections.abc import Callable, Sequence

from sukoon import tools
from sukoon.errors import Canceled


class FfmpegError(Exception):
    pass


class FfmpegTimeout(FfmpegError):
    pass


def run(
    args: Sequence[str],
    duration: float,
    on_progress: Callable[[float], None] = lambda _f: None,
    cancelled: Callable[[], bool] = lambda: False,
    timeout: float | None = None,
) -> None:
    """Runs ffmpeg with an argument list (never a shell), reporting 0..1 progress.

    Cancelling kills the process; so does running past the timeout, which scales with duration.
    """
    exe = tools.ffmpeg_path()
    if exe is None:
        raise FfmpegError("ffmpeg was not found")
    limit = timeout if timeout is not None else 120 + duration * 4
    proc = subprocess.Popen(
        [exe, "-nostdin", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-nostats", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    errors: list[str] = []
    drain = threading.Thread(target=lambda: errors.extend(proc.stderr or []), daemon=True)
    drain.start()
    started = time.monotonic()
    killed: str | None = None

    def watchdog() -> None:
        nonlocal killed
        while proc.poll() is None:
            if cancelled():
                killed = "cancel"
            elif time.monotonic() - started > limit:
                killed = "timeout"
            if killed:
                proc.kill()
                return
            time.sleep(0.1)

    guard = threading.Thread(target=watchdog, daemon=True)
    guard.start()
    for line in proc.stdout or []:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and duration > 0:
            on_progress(min(1.0, int(value) / 1e6 / duration))
    proc.wait()
    guard.join()
    drain.join(timeout=5)
    if killed == "cancel":
        raise Canceled
    if killed == "timeout":
        raise FfmpegTimeout(f"ffmpeg took longer than {limit:.0f} s and was stopped")
    if proc.returncode != 0:
        message = "".join(errors).strip()
        if "No space left on device" in message:
            raise OSError(errno.ENOSPC, "No space left on device")
        raise FfmpegError(message.splitlines()[-1] if message else f"exit {proc.returncode}")
    on_progress(1.0)
