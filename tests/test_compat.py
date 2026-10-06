import pytest

from sukoon.compat import default_container, plan
from sukoon.probe import Probe, Stream, probe


def synthetic(video="h264", audio=("aac",), subs=()):
    streams = [Stream(0, "video", video, frames=250)]
    streams += [Stream(i + 1, "audio", c, channels=2, sample_rate=48000)
                for i, c in enumerate(audio)]
    streams += [Stream(len(streams) + i, "subtitle", c) for i, c in enumerate(subs)]
    return Probe("matroska,webm", 10.0, 1000, streams)


@pytest.mark.parametrize(
    ("name", "container"),
    [("offset-0.5s.mp4", "mp4"), ("two-tracks.mkv", "mkv"), ("vp9-opus.webm", "webm"),
     ("subs-ass.mkv", "mkv"), ("vfr-rotated.mp4", "mp4")],
)
def test_default_container_matches_the_input(corpus, name, container):
    assert default_container(probe(corpus / name), name) == container


def test_same_container_never_reencodes(corpus):
    for name in ("offset-0.5s.mp4", "two-tracks.mkv", "vp9-opus.webm", "vfr-rotated.mp4"):
        p = probe(corpus / name)
        assert plan(p, 0, default_container(p, name)).reencode is None


@pytest.mark.parametrize(
    ("video", "container", "reencode"),
    [("vp9", "mov", "H.264"), ("prores", "webm", "VP9"), ("h264", "webm", "VP9"),
     ("hevc", "mp4", None), ("vp9", "webm", None), ("av1", "webm", None), ("vp8", "webm", None),
     ("prores", "mkv", None), ("vp9", "mp4", None), ("prores", "mov", None)],
)
def test_video_codec_table(video, container, reencode):
    assert plan(synthetic(video=video), 0, container).reencode == reencode


def test_reencode_needs_a_confirm_sentence():
    message = plan(synthetic(video="vp9"), 0, "mov").confirm_message
    assert message == ("The picture will be re-encoded to H.264 for MOV (about as long as the "
                       "video's duration on this machine).")
    assert plan(synthetic(), 0, "mp4").confirm_message is None


@pytest.mark.parametrize(("container", "codec"),
                         [("mp4", "aac"), ("mov", "aac"), ("mkv", "libopus"), ("webm", "libopus")])
def test_new_voice_track_encoder(container, codec):
    assert plan(synthetic(), 0, container).audio[0].codec == codec


def test_only_the_chosen_track_is_replaced():
    p = synthetic(audio=("aac", "ac3"))
    result = plan(p, 1, "mkv")
    assert [(a.action, a.codec) for a in result.audio] == [("copy", None), ("convert", "libopus")]


def test_other_tracks_convert_only_when_the_container_cannot_hold_them():
    result = plan(synthetic(audio=("aac", "ac3")), 0, "webm")
    assert [a.action for a in result.audio] == ["convert", "convert"]


def test_ass_subtitles_stay_in_mkv_and_drop_from_mp4_with_a_note():
    p = synthetic(subs=("ass",))
    assert [s.action for s in plan(p, 0, "mkv").subtitles] == ["copy"]
    to_mp4 = plan(p, 0, "mp4")
    assert to_mp4.subtitles == []
    assert to_mp4.notes == [
        "Subtitles were left out because MP4 can't hold them; choose MKV to keep them."]


@pytest.mark.parametrize(("container", "target"), [("mp4", "mov_text"), ("mov", "mov_text"),
                                                   ("webm", "webvtt")])
def test_text_subtitles_convert(container, target):
    result = plan(synthetic(subs=("subrip",)), 0, container)
    assert [(s.action, s.codec) for s in result.subtitles] == [("convert", target)]
    assert result.notes == []


def test_image_subtitles_drop_outside_mkv():
    assert plan(synthetic(subs=("hdmv_pgs_subtitle",)), 0, "mp4").subtitles == []
    assert len(plan(synthetic(subs=("hdmv_pgs_subtitle",)), 0, "mkv").subtitles) == 1


def test_attachments_only_for_mkv():
    assert plan(synthetic(), 0, "mkv").attachments
    assert not plan(synthetic(), 0, "mp4").attachments
