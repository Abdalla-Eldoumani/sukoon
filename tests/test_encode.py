import pytest

from sukoon.media.encode import default_audio_format
from sukoon.media.probe import Probe, Stream


def audio_probe(container: str, codec: str) -> Probe:
    return Probe(container, 60.0, 1000, [Stream(0, "audio", codec, channels=2, sample_rate=44100)])


@pytest.mark.parametrize(
    ("container", "codec", "expected"),
    [
        ("mp3", "mp3", "mp3"),
        ("wav", "pcm_s16le", "wav"),
        ("flac", "flac", "flac"),
        ("ipod", "alac", "flac"),
        ("matroska,webm", "wavpack", "flac"),
        ("ogg", "opus", "opus"),
        ("ogg", "vorbis", "ogg"),
        ("mov,mp4,m4a,3gp,3g2,mj2", "aac", "m4a"),
        ("matroska,webm", "ac3", "m4a"),
    ],
)
def test_the_default_output_matches_what_came_in(container, codec, expected):
    assert default_audio_format(audio_probe(container, codec)) == expected
