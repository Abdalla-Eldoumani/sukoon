import shutil
from dataclasses import dataclass
from functools import cache
from typing import Literal

DevicePreference = Literal["auto", "cpu"]


@dataclass(frozen=True)
class DeviceInfo:
    kind: Literal["cuda", "mps", "cpu"]
    label: str
    torch_version: str | None


def detect(preference: DevicePreference = "auto") -> DeviceInfo:
    try:
        import torch
    except ImportError:
        return DeviceInfo("cpu", "CPU", None)
    version = str(torch.__version__)
    if preference == "auto" and torch.cuda.is_available():
        name = str(torch.cuda.get_device_name(0)).removeprefix("NVIDIA ").removesuffix(" GPU")
        return DeviceInfo("cuda", f"CUDA · {name}", version)
    if preference == "auto" and torch.backends.mps.is_available():
        return DeviceInfo("mps", "MPS · Apple GPU", version)
    return DeviceInfo("cpu", "CPU", version)


@cache
def detect_cached(preference: DevicePreference = "auto") -> DeviceInfo:
    return detect(preference)


def nvidia_gpu_present() -> bool:
    return shutil.which("nvidia-smi") is not None
