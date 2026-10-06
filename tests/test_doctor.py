from sukoon import doctor
from sukoon.device import DeviceInfo


def run(settings):
    lines = []
    code = doctor.run(settings, out=lines.append)
    return code, "\n".join(lines)


def test_reports_every_check(settings):
    code, text = run(settings)
    assert code == 0
    for name in ("ffmpeg", "ffprobe", "encoders", "torch", "disk", "model best", "model fast"):
        assert name in text
    assert "all present" in text
    assert str(settings.home) in text


def test_missing_ffmpeg_exits_nonzero_with_install_command(settings, monkeypatch):
    monkeypatch.setenv("PATH", "")
    code, text = run(settings)
    assert code == 1
    assert "FAIL ffmpeg" in text
    assert "fix: sudo apt install ffmpeg" in text


def test_missing_encoder_is_named(settings, monkeypatch):
    monkeypatch.setattr("sukoon.tools.available_encoders", lambda: {"aac", "flac"})
    _, text = run(settings)
    assert "missing libmp3lame" in text


def test_nvidia_gpu_without_cuda_torch_prints_cuda_install(settings, monkeypatch):
    monkeypatch.setattr("sukoon.device.detect", lambda *a: DeviceInfo("cpu", "CPU", "2.14.1+cpu"))
    monkeypatch.setattr("sukoon.device.nvidia_gpu_present", lambda: True)
    _, text = run(settings)
    assert "NVIDIA GPU present but torch has no CUDA" in text
    assert "fix: uv sync --extra cuda" in text


def test_cuda_device_is_reported(settings, monkeypatch):
    monkeypatch.setattr(
        "sukoon.device.detect",
        lambda *a: DeviceInfo("cuda", "CUDA · RTX 3060 Laptop", "2.14.1+cu126"),
    )
    monkeypatch.setattr("sukoon.device.nvidia_gpu_present", lambda: True)
    _, text = run(settings)
    assert "ok   torch      2.14.1+cu126, device CUDA · RTX 3060 Laptop" in text
