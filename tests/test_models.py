import hashlib

import pytest

from sukoon.engine import AudioSeparatorEngine
from sukoon.models import (
    CHECKSUM_MESSAGE,
    MODEL_FILES,
    ModelChecksumError,
    ModelFile,
    ModelMissingError,
    is_ready,
    verify_preset,
)

CONTENT = b"pretend model weights " * 100
FILES = (
    ModelFile(
        "fast",
        "UVR-MDX-NET-Voc_FT.onnx",
        "http://127.0.0.1:1/m.onnx",
        len(CONTENT),
        hashlib.sha256(CONTENT).hexdigest(),
    ),
)


def test_registry_holds_the_three_pinned_files():
    assert [(f.preset, f.name, f.size) for f in MODEL_FILES] == [
        ("best", "vocals_mel_band_roformer.ckpt", 913106900),
        ("best", "vocals_mel_band_roformer.yaml", 944),
        ("fast", "UVR-MDX-NET-Voc_FT.onnx", 66762490),
    ]
    assert all(f.url.startswith("https://github.com/") for f in MODEL_FILES)
    assert all(len(f.sha256) == 64 for f in MODEL_FILES)


def test_a_matching_file_passes(tmp_path):
    (tmp_path / FILES[0].name).write_bytes(CONTENT)
    assert verify_preset(tmp_path, "fast", FILES) == tmp_path / "UVR-MDX-NET-Voc_FT.onnx"


def test_one_flipped_byte_deletes_the_file_and_fails(tmp_path):
    flipped = bytearray(CONTENT)
    flipped[100] ^= 0x01
    path = tmp_path / FILES[0].name
    path.write_bytes(bytes(flipped))
    with pytest.raises(ModelChecksumError, match=CHECKSUM_MESSAGE):
        verify_preset(tmp_path, "fast", FILES)
    assert not path.exists()


def test_missing_file(tmp_path):
    with pytest.raises(ModelMissingError):
        verify_preset(tmp_path, "fast", FILES)


def test_real_engine_refuses_a_tampered_model_before_loading_it(tmp_path):
    (tmp_path / FILES[0].name).write_bytes(CONTENT[:-1] + b"!")
    with pytest.raises(ModelChecksumError):
        AudioSeparatorEngine(tmp_path, FILES).prepare("fast", "cpu")
    assert not (tmp_path / FILES[0].name).exists()


def test_ready_needs_every_file_at_its_pinned_size(tmp_path):
    assert not is_ready(tmp_path, "best")
    (tmp_path / "vocals_mel_band_roformer.yaml").write_bytes(b"x" * 944)
    assert not is_ready(tmp_path, "best")
