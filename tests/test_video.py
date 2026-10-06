import functools
import json
import subprocess
import time

import numpy as np
import pytest
import soundfile as sf

from sukoon import pipeline
from sukoon.chunk import separate_chunked
from sukoon.engine import FakeEngine
from sukoon.errors import JobError
from sukoon.pipeline import Options
from sukoon.probe import probe


def ffprobe(path, *args):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", *args, str(path)],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(out.stdout)


def packet_hashes(path, selector):
    """Each packet's bytes and its time relative to the first packet of the stream.

    Relative, because Matroska remuxers may move a whole file's clock by a few milliseconds.
    """
    data = ffprobe(
        path,
        "-select_streams",
        selector,
        "-show_packets",
        "-show_data_hash",
        "MD5",
        "-show_entries",
        "packet=pts_time,data_hash",
    )
    first = float(data["packets"][0]["pts_time"])
    return [(round(float(p["pts_time"]) - first, 6), p["data_hash"]) for p in data["packets"]]


def first_video_time(path):
    data = ffprobe(
        path,
        "-select_streams",
        "v:0",
        "-show_packets",
        "-read_intervals",
        "%+2",
        "-show_entries",
        "packet=pts_time",
    )
    return min(float(p["pts_time"]) for p in data["packets"])


def first_audio_frame_time(path, track=0):
    data = ffprobe(
        path,
        "-select_streams",
        f"a:{track}",
        "-show_frames",
        "-read_intervals",
        "%+2",
        "-show_entries",
        "frame=pts_time",
    )
    return min(float(f["pts_time"]) for f in data["frames"])


def timeline(path, tmp_path, track=0):
    """Mono audio on the file's absolute clock (no rebasing), silence before the first sample."""
    out = tmp_path / f"timeline-{path.stem}-{track}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-copyts",
            "-i",
            str(path),
            "-map",
            f"0:a:{track}",
            "-af",
            "aresample=async=1:first_pts=0",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_f32le",
            str(out),
        ],
        check=True,
    )
    return sf.read(out)[0]


def speech_lag(src, out, tmp_path, track=0):
    """Seconds by which the output's speech is off from the source's, relative to the picture."""
    moved = first_video_time(out) - first_video_time(src)
    a, b = timeline(src, tmp_path, track), timeline(out, tmp_path, track)
    expected = round(moved * 44100)
    a, b = (a[-expected:], b) if expected < 0 else (a, b[expected:])
    window = 2205  # 50 ms either side of where the picture went
    n = min(len(a), len(b)) - window
    scores = [
        np.dot(a[window : n - window], b[window + k : n - window + k])
        for k in range(-window, window)
    ]
    return (int(np.argmax(scores)) - window) / 44100


def clean(corpus, tmp_path, name, **opts):
    src = corpus / name
    result = pipeline.run(
        src,
        probe(src),
        Options(**opts),
        functools.partial(separate_chunked, FakeEngine()),
        lambda: False,
        lambda *a: None,
        tmp_path / "work",
        tmp_path / "out",
    )
    return result, tmp_path / "out" / result.output


@pytest.mark.parametrize(
    ("name", "container"),
    [
        ("offset-0.5s.mp4", "mp4"),
        ("surround-5.1.mp4", "mp4"),
        ("two-tracks.mkv", "mkv"),
        ("subs-ass.mkv", "mkv"),
        ("vfr-rotated.mp4", "mp4"),
        ("vp9-opus.webm", "webm"),
        ("truncated.mp4", "mp4"),
    ],
)
def test_video_fixture_keeps_its_container_and_copies_the_picture(
    corpus, tmp_path, name, container
):
    src = corpus / name
    result, out = clean(corpus, tmp_path, name)
    assert result.format == container
    assert out.suffix == f".{container}"
    assert packet_hashes(out, "v:0") == packet_hashes(src, "v:0")


def test_rotation_and_variable_frame_timing_survive(corpus, tmp_path):
    _, out = clean(corpus, tmp_path, "vfr-rotated.mp4")
    stream = ffprobe(out, "-select_streams", "v:0", "-show_streams")["streams"][0]
    assert any(d.get("rotation") == 90 for d in stream.get("side_data_list", []))
    pts = [p[0] for p in packet_hashes(out, "v:0")]
    assert len(set(np.diff(sorted(pts)))) > 1  # still variable


# Start times are compared for AAC in MP4 and MOV, where they mean when the sound starts.
# Matroska reports an Opus track's first frame after taking off its codec delay, so there
# only the speech itself is compared, which every case checks.
SYNC_CASES = [
    ("offset-0.5s.mp4", 0, None, True),
    ("surround-5.1.mp4", 0, None, True),
    ("offset-0.5s.mp4", 0, "mov", True),
    ("two-tracks.mkv", 1, None, False),
    ("two-tracks.mkv", 0, None, False),
    ("vp9-opus.webm", 0, None, False),
    ("subs-ass.mkv", 0, "mp4", False),
    ("two-tracks.mkv", 1, "mp4", False),
    ("vp9-opus.webm", 0, "mkv", False),
    ("offset-0.5s.mp4", 0, "mkv", False),
]


@pytest.mark.parametrize(("name", "track", "fmt", "check_start"), SYNC_CASES)
def test_new_audio_stays_in_sync_with_the_picture(corpus, tmp_path, name, track, fmt, check_start):
    src = corpus / name
    _, out = clean(corpus, tmp_path, name, track=track, format=fmt)
    moved = first_video_time(out) - first_video_time(src)
    if check_start:
        start_error = (first_audio_frame_time(out, track) - moved) - first_audio_frame_time(
            src, track
        )
        assert abs(start_error) <= 0.001, f"start differs by {start_error * 1000:.2f} ms"
    lag = speech_lag(src, out, tmp_path, track)
    assert abs(lag) <= 0.001, f"lag {lag * 1000:.2f} ms"


def test_only_the_chosen_track_changes(corpus, tmp_path):
    src = corpus / "two-tracks.mkv"
    _, out = clean(corpus, tmp_path, "two-tracks.mkv", track=1)
    audio = [s for s in ffprobe(out, "-show_streams")["streams"] if s["codec_type"] == "audio"]
    assert len(audio) == 2
    assert [s["tags"].get("language") for s in audio] == ["eng", "ara"]
    assert packet_hashes(out, "a:0") == packet_hashes(src, "a:0")
    assert packet_hashes(out, "a:1") != packet_hashes(src, "a:1")
    voice = timeline(out, tmp_path, track=1)
    commentary = timeline(src, tmp_path, track=1)
    n = min(len(voice), len(commentary)) - 4410
    ratio = np.sqrt(np.mean(voice[4410:n] ** 2) / np.mean(commentary[4410:n] ** 2))
    assert 0.4 < ratio < 0.6  # the fake engine halves the chosen track


def test_ass_subtitles_kept_in_mkv(corpus, tmp_path):
    result, out = clean(corpus, tmp_path, "subs-ass.mkv")
    subs = [s for s in ffprobe(out, "-show_streams")["streams"] if s["codec_type"] == "subtitle"]
    assert [s["codec_name"] for s in subs] == ["ass"]
    assert result.notes == []


def test_ass_subtitles_dropped_from_mp4_with_the_note(corpus, tmp_path):
    result, out = clean(corpus, tmp_path, "subs-ass.mkv", format="mp4")
    types = [s["codec_type"] for s in ffprobe(out, "-show_streams")["streams"]]
    assert "subtitle" not in types
    assert result.notes == [
        "Subtitles were left out because MP4 can't hold them; choose MKV to keep them."
    ]


def test_chapters_and_container_metadata_are_carried(corpus, tmp_path):
    _, out = clean(corpus, tmp_path, "subs-ass.mkv")
    data = ffprobe(out, "-show_chapters", "-show_format")
    assert [c["tags"]["title"] for c in data["chapters"]] == ["Opening", "Ending"]
    assert data["format"]["tags"]["title"] == "Subtitled"


def test_incompatible_container_needs_a_confirm(corpus, tmp_path):
    with pytest.raises(JobError, match=r"re-encoded to H\.264 for MOV"):
        clean(corpus, tmp_path, "vp9-opus.webm", format="mov")


def test_confirmed_reencode_produces_h264(corpus, tmp_path):
    _, out = clean(corpus, tmp_path, "vp9-opus.webm", format="mov", reencode_ok=True)
    streams = ffprobe(out, "-show_streams")["streams"]
    assert [s["codec_name"] for s in streams] == ["h264", "aac"]


def test_webm_keeps_vp9_without_reencoding(corpus, tmp_path):
    src = corpus / "vp9-opus.webm"
    _, out = clean(corpus, tmp_path, "vp9-opus.webm", format="webm")
    assert packet_hashes(out, "v:0") == packet_hashes(src, "v:0")
    assert ffprobe(out, "-show_streams")["streams"][1]["codec_name"] == "opus"


@pytest.mark.parametrize("fmt", ["mp3", "m4a", "flac"])
def test_audio_only_output_from_video(corpus, tmp_path, fmt):
    _, out = clean(corpus, tmp_path, "offset-0.5s.mp4", format=fmt)
    types = [s["codec_type"] for s in ffprobe(out, "-show_streams")["streams"]]
    assert types == ["audio"]


def test_audio_file_cannot_become_video(corpus, tmp_path):
    with pytest.raises(JobError, match="no picture"):
        clean(corpus, tmp_path, "short-2s.wav", format="mp4")


@pytest.mark.parametrize("fmt", ["mp4", "mkv"])
def test_late_starting_clock_is_rebased_and_stays_in_sync(corpus, tmp_path, fmt):
    """MPEG-TS clocks start near 1.4 s; the output starts at zero with sound still on the lips."""
    src = tmp_path / "late.ts"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(corpus / "offset-0.5s.mp4"),
            "-c",
            "copy",
            "-f",
            "mpegts",
            str(src),
        ],
        check=True,
    )
    assert first_video_time(src) > 1.0
    result = pipeline.run(
        src,
        probe(src),
        Options(format=fmt),
        functools.partial(separate_chunked, FakeEngine()),
        lambda: False,
        lambda *a: None,
        tmp_path / "work",
        tmp_path / "out",
    )
    out = tmp_path / "out" / result.output
    assert first_video_time(out) < 0.1
    lag = speech_lag(src, out, tmp_path)
    assert abs(lag) <= 0.0015, f"lag {lag * 1000:.2f} ms"


def test_the_encode_shows_time_left_and_the_bar_fills_when_it_is_done(tmp_path):
    # Half a minute, so a second full pass after the bar filled would be plain to see.
    src = tmp_path / "talk.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x90:r=10:d=30",
            "-f",
            "lavfi",
            "-i",
            "sine=f=300:d=30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
    )
    seen = []
    pipeline.run(
        src,
        probe(src),
        Options(),
        functools.partial(separate_chunked, FakeEngine()),
        lambda: False,
        lambda stage, fraction, eta: seen.append((time.monotonic(), stage, fraction, eta)),
        tmp_path / "work",
        tmp_path / "out",
    )
    finished = time.monotonic()
    encoding = [s for s in seen if s[1] == "encoding"]
    assert any(eta is not None for *_, eta in encoding)
    full = next(t for t, _, fraction, _ in encoding if fraction == 1.0)
    assert finished - full < 0.3 * (full - encoding[0][0])
