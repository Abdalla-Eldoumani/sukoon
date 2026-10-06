import hashlib
import re

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
from sukoon.settings import Settings

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


def test_registry_holds_the_pinned_files():
    assert [(f.preset, f.name, f.size) for f in MODEL_FILES] == [
        ("best", "vocals_mel_band_roformer.ckpt", 913106900),
        ("best", "vocals_mel_band_roformer.yaml", 944),
        ("best", "download_checks.json", 28267),
        ("fast", "UVR-MDX-NET-Voc_FT.onnx", 66762490),
        ("fast", "download_checks.json", 28267),
        ("fast", "mdx_model_data.json", 15358),
        ("fast", "vr_model_data.json", 4380),
    ]
    assert all(len(f.sha256) == 64 for f in MODEL_FILES)


def test_every_address_is_fixed():
    """Release files, or tables read at one commit, never a branch that can move."""
    release = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/releases/download/")
    commit = re.compile(
        r"https://raw\.githubusercontent\.com/TRvlvr/application_data/[0-9a-f]{40}/"
    )
    for f in MODEL_FILES:
        assert release.match(f.url) or commit.match(f.url), f.url


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


def test_engine_scratch_lives_in_the_work_area(tmp_path):
    """Every start clears work/, so a worker killed mid-job leaves nothing behind for long."""
    settings = Settings(home=tmp_path)
    engine = AudioSeparatorEngine(settings.area("models"))
    assert engine.scratch.is_relative_to(settings.area("work"))
