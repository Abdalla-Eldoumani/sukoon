"""Real separation models on the generated fixtures. Opt in with SUKOON_TEST_MODELS=1.

The models download once into tests/fixtures/generated/models.
"""

import functools
import os

import numpy as np
import pytest
import soundfile as sf

from sukoon.jobs import pipeline
from sukoon.jobs.pipeline import Options
from sukoon.media.probe import probe
from sukoon.separation.chunk import separate_chunked
from sukoon.separation.download import download_preset
from sukoon.separation.engine import AudioSeparatorEngine

pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(
        os.environ.get("SUKOON_TEST_MODELS") != "1",
        reason="set SUKOON_TEST_MODELS=1 to run the real models",
    ),
]

THRESHOLD_DB = {"fast": 15.0, "best": 18.0}


@pytest.fixture(scope="module")
def models_dir(corpus):
    folder = corpus / "models"
    for preset in ("fast", "best"):
        download_preset(folder, preset, lambda *a: None)
    return folder


@functools.cache
def engine_for(models_dir, preset):
    engine = AudioSeparatorEngine(models_dir)
    engine.prepare(preset, "cpu")
    return engine


def si_sdr(estimate, reference):
    """Scale-invariant SDR in dB, on the mono mix of each signal."""
    est = estimate.mean(axis=1) if estimate.ndim == 2 else estimate
    ref = reference.mean(axis=1) if reference.ndim == 2 else reference
    target = (np.dot(est, ref) / np.dot(ref, ref)) * ref
    return 10 * np.log10(np.sum(target**2) / np.sum((est - target) ** 2))


def clean(corpus, tmp_path, models_dir, name, preset):
    src = corpus / name
    result = pipeline.run(
        src,
        probe(src),
        Options(preset=preset, format="wav"),
        functools.partial(separate_chunked, engine_for(models_dir, preset)),
        lambda: False,
        lambda *a: None,
        tmp_path / "work",
        tmp_path / "out",
    )
    data, rate = sf.read(tmp_path / "out" / result.output, dtype="float64")
    return result, data, rate


@pytest.mark.parametrize("preset", ["fast", "best"])
def test_speech_over_music_improves_past_the_threshold(corpus, tmp_path, models_dir, preset):
    mixture, _ = sf.read(corpus / "speech-over-music-30s.wav", dtype="float64")
    speech, _ = sf.read(corpus / "speech-clean-30s.wav", dtype="float64")
    _, voice, rate = clean(corpus, tmp_path, models_dir, "speech-over-music-30s.wav", preset)
    assert rate == 44100
    assert len(voice) == len(mixture)
    improvement = si_sdr(voice, speech) - si_sdr(mixture, speech)
    assert improvement >= THRESHOLD_DB[preset], f"{preset}: {improvement:.2f} dB"


def test_two_second_file_succeeds_with_exact_length(corpus, tmp_path, models_dir):
    source, _ = sf.read(corpus / "short-2s.wav")
    _, voice, _ = clean(corpus, tmp_path, models_dir, "short-2s.wav", "fast")
    assert len(voice) == len(source)


def test_speech_only_says_there_was_almost_no_music(corpus, tmp_path, models_dir):
    # Best, because Fast returns clean speech about 7 dB quieter, which reads as removed energy.
    result, _, _ = clean(corpus, tmp_path, models_dir, "speech-only-20s.wav", "best")
    assert pipeline.NOTE_NO_MUSIC in result.notes


def test_music_only_says_no_voices_were_found(corpus, tmp_path, models_dir):
    result, _, _ = clean(corpus, tmp_path, models_dir, "music-only-20s.wav", "fast")
    assert pipeline.NOTE_NO_VOICE in result.notes


def test_chunked_separation_is_as_good_as_whole_file(corpus, tmp_path, models_dir):
    # The model's own windows land differently when the file is cut, so the samples differ
    # everywhere; what must hold is that cutting into chunks costs no audible quality.
    mix, rate = sf.read(corpus / "speech-over-music-30s.wav", dtype="float32")
    speech, _ = sf.read(corpus / "speech-clean-30s.wav", dtype="float64")
    long = np.concatenate([mix] * 6)  # three minutes
    reference = np.concatenate([speech] * 6)
    sf.write(tmp_path / "long.wav", long, rate, subtype="FLOAT")
    engine = engine_for(models_dir, "fast")
    engine.separate(tmp_path / "long.wav", tmp_path / "whole.wav")
    separate_chunked(
        engine,
        tmp_path / "long.wav",
        tmp_path / "chunked.wav",
        tmp_path,
        lambda: False,
        lambda d, t: None,
    )
    whole, _ = sf.read(tmp_path / "whole.wav", dtype="float64")
    chunked, _ = sf.read(tmp_path / "chunked.wav", dtype="float64")
    assert len(chunked) == len(long)
    assert not np.isnan(chunked).any()
    n = min(len(whole), len(chunked))
    assert si_sdr(chunked[:n], reference[:n]) > si_sdr(whole[:n], reference[:n]) - 1.0
