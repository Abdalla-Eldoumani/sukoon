import shutil
import subprocess
import sys

REQUIRED_ENCODERS = (
    "libmp3lame",
    "aac",
    "libopus",
    "libvorbis",
    "flac",
    "pcm_s24le",
    "libx264",
    "libvpx-vp9",
)


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def ffmpeg_install_command() -> str:
    if sys.platform == "win32":
        return "winget install Gyan.FFmpeg"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg"


def node_install_command() -> str:
    if sys.platform == "win32":
        return "winget install OpenJS.NodeJS.LTS"
    if sys.platform == "darwin":
        return "brew install node"
    return "install Node.js 22 or newer from nodejs.org or your package manager"


def node_version() -> str | None:
    """`node --version`, for example v24.7.0. yt-dlp runs YouTube's checks in it."""
    exe = shutil.which("node")
    if exe is None:
        return None
    out = subprocess.run(
        [exe, "--version"], capture_output=True, text=True, timeout=20, check=False
    )
    return out.stdout.strip() or None


def ffmpeg_version() -> str | None:
    exe = ffmpeg_path()
    if exe is None:
        return None
    out = subprocess.run(
        [exe, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20, check=False
    )
    first = out.stdout.splitlines()[0] if out.stdout else ""
    return first.removeprefix("ffmpeg version ").split(" ")[0] or None


def available_encoders() -> set[str]:
    exe = ffmpeg_path()
    if exe is None:
        return set()
    out = subprocess.run(
        [exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20, check=False
    )
    names = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        # Encoder lines look like " A....D libmp3lame  ..."; the legend above them has "=".
        if len(parts) >= 2 and len(parts[0]) == 6 and "=" not in line:
            names.add(parts[1])
    return names
