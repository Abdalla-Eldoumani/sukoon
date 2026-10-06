import shutil
from collections.abc import Callable

from sukoon import device, models, tools
from sukoon.settings import GB, Settings


def run(settings: Settings, out: Callable[[str], None] = print) -> int:
    """Prints one line per check and the command that fixes anything missing."""
    failed = False

    def line(ok: bool | None, name: str, detail: str, fix: str | None = None) -> None:
        mark = {True: "ok  ", False: "FAIL", None: "--  "}[ok]
        out(f"{mark} {name:<10} {detail}")
        if ok is not True and fix:
            out(f"     {'':<10} fix: {fix}")

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
    failed |= ffmpeg is None or ffprobe is None

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
        line(False, "torch", "not installed", "uv sync --extra cpu (or --extra cuda for NVIDIA)")
    elif device.nvidia_gpu_present() and info.kind != "cuda":
        line(
            False,
            "torch",
            f"{info.torch_version}, device {info.label}: NVIDIA GPU present but torch has no CUDA",
            "uv sync --extra cuda",
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
