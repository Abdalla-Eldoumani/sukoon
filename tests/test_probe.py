import subprocess

import pytest

from sukoon.media.probe import NO_SOUND, PLAYLIST, UNREADABLE, Probe, Rejected, probe


@pytest.mark.parametrize(
    ("name", "kind", "audio_tracks"),
    [
        ("speech-over-music-30s.wav", "audio", 1),
        ("song-with-cover.mp3", "audio", 1),
        ("hires-96k.flac", "audio", 1),
        ("mono-22k.wav", "audio", 1),
        ("surround-5.1.mp4", "video", 1),
        ("two-tracks.mkv", "video", 2),
        ("offset-0.5s.mp4", "video", 1),
        ("subs-ass.mkv", "video", 1),
        ("vfr-rotated.mp4", "video", 1),
        ("vp9-opus.webm", "video", 1),
        ("truncated.mp4", "video", 1),
    ],
)
def test_classifies_by_content(corpus, name, kind, audio_tracks):
    p = probe(corpus / name)
    assert p.kind == kind
    assert len(p.audio) == audio_tracks


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("empty.mp4", UNREADABLE),
        ("text-renamed.mp4", UNREADABLE),
        ("random-bytes.bin", UNREADABLE),
        ("video-no-audio.mp4", NO_SOUND),
        ("playlist-local.m3u8", PLAYLIST),
        ("playlist-remote.m3u8", PLAYLIST),
    ],
)
def test_rejects_with_a_specific_sentence(corpus, name, message):
    with pytest.raises(Rejected) as err:
        probe(corpus / name)
    assert err.value.message == message


def test_cover_art_is_not_video(corpus):
    p = probe(corpus / "song-with-cover.mp3")
    assert p.video == []
    assert len(p.covers) == 1


def test_reads_stream_details(corpus):
    p = probe(corpus / "two-tracks.mkv")
    assert [(s.language, s.title) for s in p.audio] == [("eng", "Main"), ("ara", "Commentary")]
    assert p.default_audio() == 0
    assert abs(p.duration - 10.0) < 0.05
    assert p.audio[0].sample_rate == 48000


def test_offset_audio_start_time(corpus):
    assert probe(corpus / "offset-0.5s.mp4").audio[0].start_time > 0.4


def test_chapters_are_counted(corpus):
    assert probe(corpus / "subs-ass.mkv").chapters == 2


def test_duration_limit(corpus):
    with pytest.raises(Rejected, match=r"longer than 0\.00277778 hours"):
        probe(corpus / "speech-over-music-30s.wav", max_duration=10)


def test_concat_list_is_rejected_by_content(tmp_path, corpus):
    lst = tmp_path / "list.txt"
    lst.write_text(f"ffconcat version 1.0\nfile '{corpus / 'short-2s.wav'}'\n")
    with pytest.raises(Rejected, match="playlist"):
        probe(lst)


def test_probe_round_trips_through_json(corpus):
    p = probe(corpus / "two-tracks.mkv")
    assert Probe.from_json(p.to_json()) == p


@pytest.mark.parametrize(
    ("format_name", "denied"),
    [
        ("hls", True),
        ("concat", True),
        ("sdp", True),
        ("rtsp", True),
        ("tee", True),
        ("dash", True),
        ("imf", True),
        ("image2", True),
        ("png_pipe", True),
        ("jpeg_pipe", True),
        ("mov,mp4,m4a,3gp,3g2,mj2", False),
        ("matroska,webm", False),
        ("mp3", False),
    ],
)
def test_format_denylist(format_name, denied):
    from sukoon.media.probe import is_denied

    assert is_denied(format_name) is denied


@pytest.mark.parametrize(
    ("head", "found"),
    [
        (b'<MPD profiles="urn:mpeg:dash:profile:isoff-live:2011">', True),
        (b'<mpd profiles="urn:MPEG:DASH:PROFILE:full:2011">', True),
        (b'<MPD profiles="urn:3GPP:PSS:profile:DASH1">', True),
        (
            b"<!--" + b" " * 300_000 + b'--><MPD profiles="urn:mpeg:dash:profile:isoff-live:2011">',
            True,
        ),
        (b"<MPD>", False),
        (b'profiles="urn:mpeg:dash:profile:isoff-live:2011"', False),
        (b"ID3\x04\x00" + bytes(range(256)) * 40, False),
    ],
)
def test_manifest_markers_match_what_ffmpeg_probes_for(head, found):
    from sukoon.media.probe import is_manifest

    assert is_manifest(head) is found


def test_a_raw_aac_length_is_counted_not_guessed(tmp_path):
    # ffprobe guesses a raw AAC file's length from its first frames' bitrate, and a quiet
    # start makes that guess more than twice too long.
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
    result = probe(src)
    assert abs(result.duration - 12.0) < 0.05
    assert abs(result.audio[0].duration - 12.0) < 0.05
