import os
import stat

import pytest

from sukoon import doctor
from sukoon.device import DeviceInfo

ALL_ENCODERS = "libmp3lame aac libopus libvorbis flac pcm_s24le libx264 libvpx-vp9"


def fake_tool(folder, name, body):
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def fake_path(tmp_path, monkeypatch):
    """A PATH holding only fake tools, so each test decides what the machine has."""
    folder = tmp_path / "bin"
    folder.mkdir()
    monkeypatch.setenv("PATH", str(folder))
    return folder


def with_ffmpeg(folder, encoders=ALL_ENCODERS):
    lines = "\\n".join(f" A....D {e:<20} test" for e in encoders.split())
    fake_tool(
        folder,
        "ffmpeg",
        f"""case "$*" in
  *-version*) echo "ffmpeg version 9.9-test Copyright";;
  *-encoders*) printf 'Encoders:\\n A..... = Audio\\n ------\\n{lines}\\n';;
esac
""",
    )
    fake_tool(folder, "ffprobe", "exit 0\n")


@pytest.fixture
def cpu_torch(monkeypatch):
    # Stands in for torch itself, which is the boundary here.
    monkeypatch.setattr("sukoon.device.detect", lambda *a: DeviceInfo("cpu", "CPU", "2.14.1+cpu"))


def run(settings):
    lines = []
    code = doctor.run(settings, out=lines.append)
    return code, "\n".join(lines)


pytestmark = pytest.mark.skipif(os.name == "nt", reason="fake tools are shell scripts")


def test_reports_every_check(settings, fake_path, cpu_torch):
    with_ffmpeg(fake_path)
    code, text = run(settings)
    assert code == 0
    for name in ("ffmpeg", "ffprobe", "encoders", "torch", "disk", "model best", "model fast"):
        assert name in text
    assert "ok   ffmpeg     9.9-test" in text
    assert "all present" in text
    assert str(settings.home) in text


def test_missing_ffmpeg_exits_nonzero_with_install_command(settings, fake_path, cpu_torch):
    code, text = run(settings)
    assert code == 1
    assert "FAIL ffmpeg" in text
    assert "fix: sudo apt install ffmpeg" in text


def test_missing_encoder_is_named(settings, fake_path, cpu_torch):
    with_ffmpeg(fake_path, encoders="aac flac pcm_s24le")
    code, text = run(settings)
    assert code == 1
    assert "missing libmp3lame, libopus, libvorbis, libx264, libvpx-vp9" in text


def test_nvidia_gpu_without_cuda_torch_prints_cuda_install(settings, fake_path, cpu_torch):
    with_ffmpeg(fake_path)
    fake_tool(fake_path, "nvidia-smi", "exit 0\n")
    _, text = run(settings)
    assert "NVIDIA GPU present but torch has no CUDA" in text
    assert "fix: uv sync --extra cuda" in text


def test_cuda_device_is_reported(settings, fake_path, monkeypatch):
    with_ffmpeg(fake_path)
    fake_tool(fake_path, "nvidia-smi", "exit 0\n")
    monkeypatch.setattr(
        "sukoon.device.detect",
        lambda *a: DeviceInfo("cuda", "CUDA · RTX 3060 Laptop", "2.14.1+cu126"),
    )
    _, text = run(settings)
    assert "ok   torch      2.14.1+cu126, device CUDA · RTX 3060 Laptop" in text


def test_missing_torch_fails_with_install_command(settings, fake_path, monkeypatch):
    with_ffmpeg(fake_path)
    monkeypatch.setattr("sukoon.device.detect", lambda *a: DeviceInfo("cpu", "CPU", None))
    code, text = run(settings)
    assert code == 1
    assert "fix: uv sync --extra cpu" in text
