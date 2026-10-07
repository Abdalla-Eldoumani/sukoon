import subprocess

import pytest
import soundfile as sf

from sukoon.errors import Canceled, JobError
from sukoon.media.decode import decode
from sukoon.media.probe import probe

never = lambda: False  # noqa: E731


def run(corpus, tmp_path, name, track=0, cancelled=never):
    src = corpus / name
    out = tmp_path / "mixture.wav"
    seen = []
    result = decode(src, probe(src), track, out, seen.append, cancelled)
    return result, out, seen


def test_decodes_to_44k_stereo_float_with_exact_length(corpus, tmp_path):
    result, out, seen = run(corpus, tmp_path, "speech-over-music-30s.wav")
    info = sf.info(str(out))
    assert (info.samplerate, info.channels, info.subtype) == (44100, 2, "FLOAT")
    assert info.frames == 30 * 44100 == result.frames
    assert not result.partial
    assert seen[-1] == 1.0


def test_mono_22k_becomes_stereo_44k(corpus, tmp_path):
    result, out, _ = run(corpus, tmp_path, "mono-22k.wav")
    info = sf.info(str(out))
    assert (info.samplerate, info.channels) == (44100, 2)
    assert abs(result.seconds - 5.0) < 0.001


def test_surround_is_mixed_down(corpus, tmp_path):
    _, out, _ = run(corpus, tmp_path, "surround-5.1.mp4")
    assert sf.info(str(out)).channels == 2


def test_second_track_is_decoded_on_request(corpus, tmp_path):
    first, _, _ = run(corpus, tmp_path, "two-tracks.mkv", track=0)
    second, out, _ = run(corpus, tmp_path, "two-tracks.mkv", track=1)
    assert abs(first.seconds - 10.0) < 0.05
    assert abs(second.seconds - 10.0) < 0.05
    assert sf.info(str(out)).channels == 2


def test_truncated_file_continues_with_what_decoded(corpus, tmp_path):
    result, _, _ = run(corpus, tmp_path, "truncated.mp4")
    assert result.partial
    assert 5.0 < result.seconds < 9.5


def test_decode_under_half_the_duration_fails(corpus, tmp_path):
    # WEBM keeps its duration up front, so a cut file still probes.
    data = (corpus / "vp9-opus.webm").read_bytes()
    short = tmp_path / "short.webm"
    short.write_bytes(data[: len(data) // 3])
    with pytest.raises(JobError, match="damaged after"):
        decode(short, probe(short), 0, tmp_path / "m.wav", lambda f: None, never)


def test_cancel_kills_the_decode(corpus, tmp_path):
    with pytest.raises(Canceled):
        run(corpus, tmp_path, "speech-over-music-30s.wav", cancelled=lambda: True)


def test_a_duration_guessed_from_the_bitrate_is_not_damage(tmp_path):
    # Raw AAC has no length of its own; ffprobe guesses one from the first frames' bitrate,
    # which a quiet start pulls far from the truth.
    src = tmp_path / "talk.aac"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo:d=3",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=r=44100:d=9",
            "-filter_complex",
            "[1]aformat=channel_layouts=stereo[n];[0][n]concat=n=2:v=0:a=1",
            "-c:a",
            "aac",
            "-f",
            "adts",
            str(src),
        ],
        check=True,
    )
    result = decode(src, probe(src), 0, tmp_path / "m.wav", lambda f: None, never)
    assert not result.partial
    assert abs(result.seconds - 12.0) < 0.1
