import errno
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import soundfile as sf

from sukoon.device import DevicePreference
from sukoon.models import MODEL_FILES, ModelFile, Preset, verify_preset


class OutOfMemory(Exception):
    """The GPU ran out of memory on one chunk; the caller retries that chunk on the CPU."""


class Engine(Protocol):
    def prepare(self, preset: Preset, device: DevicePreference) -> None: ...

    def separate(self, mixture_wav: Path, voice_wav: Path, *, on_cpu: bool = False) -> None: ...


Failure = Literal["raise", "oom", "hang", "exit", "disk_full"]


@dataclass
class FakeEngine:
    """Stands in for the model: the voice is the input at half level.

    `fail` injects a failure on the call numbered `fail_on` (1-based); `oom` fails only on the GPU.
    """

    delay: float = 0.0
    fail: Failure | None = None
    fail_on: int = 1
    calls: int = 0

    def prepare(self, preset: Preset, device: DevicePreference) -> None:
        pass

    def separate(self, mixture_wav: Path, voice_wav: Path, *, on_cpu: bool = False) -> None:
        self.calls += 1
        if self.fail and self.calls == self.fail_on:
            if self.fail == "raise":
                raise RuntimeError("fake engine failure")
            if self.fail == "oom" and not on_cpu:
                raise OutOfMemory("CUDA out of memory")
            if self.fail == "hang":
                time.sleep(3600)
            if self.fail == "exit":
                os._exit(1)
            if self.fail == "disk_full":
                raise OSError(errno.ENOSPC, "No space left on device")
        if self.delay:
            time.sleep(self.delay)
        data, rate = sf.read(mixture_wav, dtype="float32", always_2d=True)
        sf.write(voice_wav, data * np.float32(0.5), rate, subtype="FLOAT")


class AudioSeparatorEngine:
    """Wraps audio-separator. Only ever handed a model path that passed the hash check."""

    def __init__(self, models_dir: Path, files: tuple[ModelFile, ...] = MODEL_FILES) -> None:
        self.models_dir = models_dir
        self.files = files
        self.model: Path | None = None
        # In the data folder's work area, which every start clears, so a killed worker's
        # folder doesn't outlive the next start.
        work = models_dir.parent / "work"
        work.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix="engine-", dir=work))
        self.gpu: Any = None
        self.cpu: Any = None

    def _separator(self, force_cpu: bool) -> Any:
        from audio_separator.separator import Separator

        if self.model is None:
            raise RuntimeError("prepare() must run before separate()")
        sep = Separator(
            log_level=logging.WARNING,
            output_dir=str(self.scratch),
            model_file_dir=str(self.models_dir),
            output_format="WAV",
            output_single_stem="Vocals",
        )
        if force_cpu:
            import torch

            sep.torch_device = torch.device("cpu")
            sep.onnx_execution_provider = ["CPUExecutionProvider"]
        sep.load_model(model_filename=self.model.name)
        return sep

    def prepare(self, preset: Preset, device: DevicePreference) -> None:
        # Hashed before every first load in this process; a swapped file never reaches torch.
        self.model = verify_preset(self.models_dir, preset, self.files)
        self.cpu = self._separator(force_cpu=True) if device == "cpu" else None
        self.gpu = None if device == "cpu" else self._separator(force_cpu=False)

    def separate(self, mixture_wav: Path, voice_wav: Path, *, on_cpu: bool = False) -> None:
        if on_cpu or self.gpu is None:
            if self.cpu is None:
                self.cpu = self._separator(force_cpu=True)
            sep = self.cpu
        else:
            sep = self.gpu
        try:
            names = sep.separate(str(mixture_wav))
        except Exception as exc:
            if sep is self.gpu and _is_cuda_oom(exc):
                _empty_cuda_cache()
                raise OutOfMemory(str(exc)) from exc
            raise
        # The stem's name differs between models, so the returned path is the only safe one.
        produced = Path(names[0])
        if not produced.is_absolute():
            produced = self.scratch / produced
        shutil.move(produced, voice_wav)


def _is_cuda_oom(exc: BaseException) -> bool:
    try:
        import torch
    except ImportError:
        return False
    return isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()


def _empty_cuda_cache() -> None:
    import torch

    torch.cuda.empty_cache()
