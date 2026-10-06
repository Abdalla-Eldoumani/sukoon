import errno
import functools
import json
import subprocess

import pytest

from sukoon import pipeline
from sukoon.chunk import separate_chunked
from sukoon.engine import FakeEngine
from sukoon.errors import Canceled, JobError
from sukoon.pipeline import Options
from sukoon.probe import probe

never = functools.partial(bool, False)


def ffprobe(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(out.stdout)


def clean(corpus, tmp_path, name, engine=None, cancelled=never, **opts):
    src = corpus / name
    stages = []
    result = pipeline.run(
        src,
        probe(src),
        Options(**opts),
        functools.partial(separate_chunked, engine or FakeEngine()),
        cancelled,
        lambda stage, f, d, t: stages.append((stage, f)),
        tmp_path / "work",
        tmp_path / "out",
    )
    return result, tmp_path / "out" / result.output, stages


# name, expected format, rate (source capped at 48 kHz), channels
AUDIO = [
    ("speech-over-music-30s.wav", "wav", 44100, 2),
    ("song-with-cover.mp3", "mp3", 44100, 2),
    ("mono-22k.wav", "wav", 22050, 1),
    ("hires-96k.flac", "flac", 48000, 2),
    ("short-2s.wav", "wav", 44100, 2),
    ("music-only-20s.wav", "wav", 44100, 2),
]


@pytest.mark.parametrize(("name", "fmt", "rate", "channels"), AUDIO)
def test_audio_fixture_round_trip(corpus, tmp_path, name, fmt, rate, channels):
    seconds = float(ffprobe(corpus / name)["format"]["duration"])
    result, out, _ = clean(corpus, tmp_path, name)
    assert result.format == fmt
    assert out.suffix == f".{fmt}"
    info = ffprobe(out)
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert int(audio["sample_rate"]) == rate
    assert audio["channels"] == channels
    assert abs(float(info["format"]["duration"]) - seconds) <= 0.001


@pytest.mark.parametrize(
    ("fmt", "codec", "rate", "check"),
    [
        ("mp3", "mp3", 44100, lambda s: True),
        ("m4a", "aac", 44100, lambda s: 200_000 <= int(s["bit_rate"]) <= 320_000),
        ("wav", "pcm_s24le", 44100, lambda s: True),
        ("flac", "flac", 44100, lambda s: s["bits_per_raw_sample"] == "24"),
        ("opus", "opus", 48000, lambda s: True),
        ("ogg", "vorbis", 44100, lambda s: True),
    ],
)
def test_format_matrix(corpus, tmp_path, fmt, codec, rate, check):
    _, out, _ = clean(corpus, tmp_path, "speech-over-music-30s.wav", format=fmt)
    stream = ffprobe(out)["streams"][0]
    assert stream["codec_name"] == codec
    assert int(stream["sample_rate"]) == rate
    assert check(stream)


def test_mp3_is_vbr_v0(corpus, tmp_path):
    _, out, _ = clean(corpus, tmp_path, "song-with-cover.mp3")
    # V0 averages well above 200 kbps on full-band material.
    assert int(ffprobe(out)["format"]["bit_rate"]) > 180_000


@pytest.mark.parametrize("fmt", ["mp3", "m4a", "flac"])
def test_cover_art_is_carried(corpus, tmp_path, fmt):
    _, out, _ = clean(corpus, tmp_path, "song-with-cover.mp3", format=fmt)
    streams = ffprobe(out)["streams"]
    covers = [s for s in streams if s["codec_type"] == "video"]
    assert len(covers) == 1
    assert covers[0]["disposition"]["attached_pic"] == 1


def test_tags_are_carried(corpus, tmp_path):
    _, out, _ = clean(corpus, tmp_path, "song-with-cover.mp3")
    tags = {k.lower(): v for k, v in ffprobe(out)["format"]["tags"].items()}
    assert tags["title"] == "Test song"


def test_surround_becomes_stereo_with_a_note(corpus, tmp_path):
    result, out, _ = clean(corpus, tmp_path, "surround-5.1.mp4", format="m4a")
    assert ffprobe(out)["streams"][0]["channels"] == 2
    assert pipeline.NOTE_SURROUND in result.notes


def test_truncated_file_gets_the_damage_note(corpus, tmp_path):
    result, _, _ = clean(corpus, tmp_path, "truncated.mp4", format="m4a")
    assert any(n.startswith("The source file is damaged after 00:0") for n in result.notes)


def test_silent_voice_gets_the_no_voice_note(corpus, tmp_path):
    class Silent(FakeEngine):
        def separate(self, mixture_wav, voice_wav, *, on_cpu=False):
            import soundfile as sf

            data, rate = sf.read(mixture_wav, dtype="float32")
            sf.write(voice_wav, data * 0, rate, subtype="FLOAT")

    result, _, _ = clean(corpus, tmp_path, "music-only-20s.wav", engine=Silent())
    assert pipeline.NOTE_NO_VOICE in result.notes


def test_untouched_input_gets_the_no_music_note(corpus, tmp_path):
    class Identity(FakeEngine):
        def separate(self, mixture_wav, voice_wav, *, on_cpu=False):
            import shutil

            shutil.copy(mixture_wav, voice_wav)

    result, _, _ = clean(corpus, tmp_path, "speech-only-20s.wav", engine=Identity())
    assert pipeline.NOTE_NO_MUSIC in result.notes


def test_stages_run_in_order_and_progress_only_rises(corpus, tmp_path):
    _, _, stages = clean(corpus, tmp_path, "speech-over-music-30s.wav")
    order = [s for i, (s, _) in enumerate(stages) if i == 0 or stages[i - 1][0] != s]
    assert order == ["decoding", "separating", "encoding"]
    fractions = [f for _, f in stages]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_scratch_is_removed_on_success_and_on_failure(corpus, tmp_path):
    clean(corpus, tmp_path, "short-2s.wav")
    assert not (tmp_path / "work").exists()
    with pytest.raises(RuntimeError):
        clean(corpus, tmp_path, "short-2s.wav", engine=FakeEngine(fail="raise"))
    assert not (tmp_path / "work").exists()


def test_cancel_leaves_no_output(corpus, tmp_path):
    with pytest.raises(Canceled):
        clean(corpus, tmp_path, "speech-over-music-30s.wav", cancelled=lambda: True)
    assert list((tmp_path / "out").iterdir()) == []
    assert not (tmp_path / "work").exists()


def test_disk_full_fails_cleanly(corpus, tmp_path):
    class Full(FakeEngine):
        def separate(self, mixture_wav, voice_wav, *, on_cpu=False):
            raise OSError(errno.ENOSPC, "No space left on device")

    with pytest.raises(JobError, match=r"The disk is full\."):
        clean(corpus, tmp_path, "short-2s.wav", engine=Full())
    assert list((tmp_path / "out").iterdir()) == []
    assert not (tmp_path / "work").exists()


def test_cpu_fallback_is_noted(corpus, tmp_path):
    result, _, _ = clean(corpus, tmp_path, "short-2s.wav", engine=FakeEngine(fail="oom"))
    assert pipeline.NOTE_CPU in result.notes
