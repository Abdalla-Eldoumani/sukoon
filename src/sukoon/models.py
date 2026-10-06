import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Preset = Literal["best", "fast"]
PRESETS: tuple[Preset, ...] = ("best", "fast")


@dataclass(frozen=True)
class ModelFile:
    preset: Preset
    name: str
    url: str
    size: int
    sha256: str


_ASEP = "https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs"
_UVR = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models"

# The only addresses models are ever fetched from, with hashes taken 2026-10-05.
MODEL_FILES: tuple[ModelFile, ...] = (
    ModelFile(
        "best",
        "vocals_mel_band_roformer.ckpt",
        f"{_ASEP}/vocals_mel_band_roformer.ckpt",
        913106900,
        "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e",
    ),
    ModelFile(
        "best",
        "vocals_mel_band_roformer.yaml",
        f"{_ASEP}/vocals_mel_band_roformer.yaml",
        944,
        "b958b29c8f7195f0d86bee6759a33980db675c4ecaf2fcaa80fa125828e6cd38",
    ),
    ModelFile(
        "fast",
        "UVR-MDX-NET-Voc_FT.onnx",
        f"{_UVR}/UVR-MDX-NET-Voc_FT.onnx",
        66762490,
        "534b2070fcc7df514b13ef660dc8cbb328679c2374d04354a5c42bb14ecce111",
    ),
)

# The file audio-separator is asked to load for each preset.
PRIMARY: dict[Preset, str] = {
    "best": "vocals_mel_band_roformer.ckpt",
    "fast": "UVR-MDX-NET-Voc_FT.onnx",
}

LABELS: dict[Preset, str] = {"best": "Best", "fast": "Fast"}


def files_for(preset: Preset) -> tuple[ModelFile, ...]:
    return tuple(f for f in MODEL_FILES if f.preset == preset)


def preset_size(preset: Preset) -> int:
    return sum(f.size for f in files_for(preset))


def is_ready(models_dir: Path, preset: Preset) -> bool:
    """Every file is in place at its pinned size; the hash is checked before loading."""
    for f in files_for(preset):
        path = models_dir / f.name
        if not path.is_file() or path.stat().st_size != f.size:
            return False
    return True


def ready_presets(models_dir: Path) -> dict[Preset, bool]:
    return {p: is_ready(models_dir, p) for p in PRESETS}


CHECKSUM_MESSAGE = "The model file didn't match its expected checksum and was removed."


class ModelChecksumError(Exception):
    pass


class ModelMissingError(Exception):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def verify_preset(
    models_dir: Path, preset: Preset, files: tuple[ModelFile, ...] = MODEL_FILES
) -> Path:
    """Checks every file of a preset against its pinned hash, deleting any that differ.

    Returns the path to hand to the engine. This is the only way a model path reaches it.
    """
    for f in (f for f in files if f.preset == preset):
        path = models_dir / f.name
        if not path.is_file():
            raise ModelMissingError(f"{f.name} is not downloaded")
        if path.stat().st_size != f.size or sha256_of(path) != f.sha256:
            path.unlink(missing_ok=True)
            raise ModelChecksumError(CHECKSUM_MESSAGE)
    return models_dir / PRIMARY[preset]
