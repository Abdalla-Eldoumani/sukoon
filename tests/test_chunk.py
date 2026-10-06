import numpy as np
import pytest
import soundfile as sf

from sukoon.chunk import Canceled, separate_chunked, windows
from sukoon.engine import FakeEngine

SR = 44100


def mixture(path, seconds, seed=1):
    rng = np.random.default_rng(seed)
    data = (rng.standard_normal((int(seconds * SR), 2)) * 0.1).astype(np.float32)
    sf.write(path, data, SR, subtype="FLOAT")
    return data


class LengthRecorder(FakeEngine):
    def __init__(self):
        super().__init__()
        self.lengths = []

    def separate(self, mixture_wav, voice_wav, *, on_cpu=False):
        self.lengths.append(sf.info(str(mixture_wav)).frames)
        super().separate(mixture_wav, voice_wav, on_cpu=on_cpu)


def test_windows_cover_the_file_with_four_second_overlaps():
    plan = windows(130 * SR, SR)
    assert plan == [(0, 60 * SR), (56 * SR, 60 * SR), (112 * SR, 18 * SR)]
    assert windows(30 * SR, SR) == [(0, 30 * SR)]
    assert windows(60 * SR, SR) == [(0, 60 * SR)]


def test_chunked_equals_whole_file_on_the_fake_engine(tmp_path):
    data = mixture(tmp_path / "mix.wav", 180)
    report = separate_chunked(
        FakeEngine(),
        tmp_path / "mix.wav",
        tmp_path / "voice.wav",
        tmp_path,
        lambda: False,
        lambda d, t: None,
    )
    voice, rate = sf.read(tmp_path / "voice.wav", dtype="float32")
    assert rate == SR
    assert voice.shape == data.shape
    np.testing.assert_allclose(voice, data * 0.5, atol=1e-6)
    assert report.chunks == 4


def test_progress_reports_each_chunk(tmp_path):
    mixture(tmp_path / "mix.wav", 130)
    seen = []
    separate_chunked(
        FakeEngine(),
        tmp_path / "mix.wav",
        tmp_path / "voice.wav",
        tmp_path,
        lambda: False,
        lambda d, t: seen.append((d, t)),
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_short_input_is_padded_to_ten_seconds_and_trimmed_back(tmp_path):
    data = mixture(tmp_path / "mix.wav", 2)
    engine = LengthRecorder()
    separate_chunked(
        engine,
        tmp_path / "mix.wav",
        tmp_path / "voice.wav",
        tmp_path,
        lambda: False,
        lambda d, t: None,
    )
    assert engine.lengths == [10 * SR]
    assert sf.info(str(tmp_path / "voice.wav")).frames == len(data)


def test_cancel_lands_between_chunks(tmp_path):
    mixture(tmp_path / "mix.wav", 130)
    engine = LengthRecorder()
    done = []
    with pytest.raises(Canceled):
        separate_chunked(
            engine,
            tmp_path / "mix.wav",
            tmp_path / "voice.wav",
            tmp_path,
            lambda: len(done) == 1,
            lambda d, t: done.append(d),
        )
    assert len(engine.lengths) == 1


def test_gpu_out_of_memory_retries_that_chunk_on_cpu(tmp_path):
    data = mixture(tmp_path / "mix.wav", 70)
    report = separate_chunked(
        FakeEngine(fail="oom", fail_on=1),
        tmp_path / "mix.wav",
        tmp_path / "voice.wav",
        tmp_path,
        lambda: False,
        lambda d, t: None,
    )
    assert report.cpu_fallbacks == 1
    voice, _ = sf.read(tmp_path / "voice.wav", dtype="float32")
    np.testing.assert_allclose(voice, data * 0.5, atol=1e-6)
