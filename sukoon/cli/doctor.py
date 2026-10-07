import importlib.metadata
import re
import shutil
from collections.abc import Callable
from datetime import date

from sukoon import device, models, tools
from sukoon.links import UPDATE
from sukoon.settings import GB, Settings

# Sites change often enough that a yt-dlp this old starts to fail on some of them.
STALE_DAYS = 60
NODE_MAJOR = 22


def age_in_days(version: str, today: date) -> int | None:
    """yt-dlp versions are release dates, such as 2026.8.19."""
    try:
        year, month, day = (int(part) for part in version.split(".")[:3])
        return (today - date(year, month, day)).days
    except ValueError:
        return None


def node_major(version: str) -> int | None:
    match = re.match(r"v?(\d+)\.", version.strip())
    return int(match.group(1)) if match else None


def installed(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def run(settings: Settings, out: Callable[[str], None] = print, today: date | None = None) -> int:
    """Prints one line per check and the command that fixes anything missing; 1 if any failed."""
    failed = False

    def line(ok: bool | None, name: str, detail: str, fix: str | None = None) -> None:
        nonlocal failed
        failed |= ok is False
        mark = {True: "ok  ", False: "FAIL", None: "--  "}[ok]
        out(f"{mark} {name:<10} {detail}")
        if ok is not True and fix:
            out(f"     {'':<10} {'fix' if ok is False else 'note'}: {fix}")

    ffmpeg = tools.ffmpeg_path()
    ffprobe = tools.ffprobe_path()
    install = tools.ffmpeg_install_command()
    line(
        ffmpeg is not None,
        "ffmpeg",
        f"{tools.ffmpeg_version()} at {ffmpeg}" if ffmpeg else "not found on PATH",
        install,
    )
    line(ffprobe is not None, "ffprobe", str(ffprobe) if ffprobe else "not found on PATH", install)

    if ffmpeg:
        have = tools.available_encoders()
        missing = [e for e in tools.REQUIRED_ENCODERS if e not in have]
        line(
            not missing,
            "encoders",
            "all present" if not missing else "missing " + ", ".join(missing),
            f"install a full ffmpeg build ({install})",
        )

    info = device.detect()
    if info.torch_version is None:
        line(False, "torch", "not installed", "uv sync")
    elif device.nvidia_gpu_present() and info.kind != "cuda":
        line(
            False,
            "torch",
            f"{info.torch_version}, device {info.label}: NVIDIA GPU present but torch has no CUDA",
            "run uv sync, then update the NVIDIA driver if it still says CPU",
        )
    else:
        line(True, "torch", f"{info.torch_version}, device {info.label}")

    settings.home.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(settings.home).free
    line(
        free > 2 * GB,
        "disk",
        f"{free / GB:.1f} GB free in {settings.home}",
        "free some space on this drive or set SUKOON_HOME to another drive",
    )

    ytdlp = installed("yt-dlp")
    if ytdlp is None:
        line(False, "yt-dlp", "not installed", "uv sync")
    else:
        age = age_in_days(ytdlp, today or date.today())
        fresh = age is not None and age < STALE_DAYS
        detail = f"{ytdlp}, {age} days old" if age is not None else ytdlp
        line(fresh or None, "yt-dlp", detail, f"links may fail as sites change; update: {UPDATE}")
    ejs = installed("yt-dlp-ejs")
    line(ejs is not None, "yt-dlp-ejs", ejs or "not installed", "uv sync")
    node = tools.node_version()
    major = node_major(node or "")
    line(
        major is not None and major >= NODE_MAJOR,
        "node",
        f"{node}" if node else "not found on PATH",
        f"YouTube links need Node.js {NODE_MAJOR} or newer: {tools.node_install_command()}",
    )

    ready = models.ready_presets(settings.area("models"))
    for preset, ok in ready.items():
        size_mb = models.preset_size(preset) / 1e6
        line(
            ok or None,
            f"model {preset}",
            "downloaded" if ok else f"not downloaded ({size_mb:.0f} MB)",
            "it downloads from the app the first time you use it",
        )
    return 1 if failed else 0
