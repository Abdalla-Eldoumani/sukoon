"""Which streams each output container can hold, and what happens to the ones it cannot."""

from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Literal

from sukoon.probe import Probe

VIDEO_CONTAINERS = ("mp4", "mkv", "webm", "mov")

MUXER = {"mp4": "mp4", "mkv": "matroska", "webm": "webm", "mov": "mov"}

VIDEO_CODECS: dict[str, set[str] | None] = {
    "mp4": {"h264", "hevc", "av1", "vp9", "mpeg4", "mpeg2video", "mjpeg"},
    "mov": {"h264", "hevc", "mpeg4", "mpeg2video", "prores", "mjpeg", "dnxhd", "qtrle"},
    "mkv": None,  # Matroska holds any of them.
    "webm": {"vp8", "vp9", "av1"},
}

AUDIO_CODECS: dict[str, set[str] | None] = {
    "mp4": {"aac", "mp3", "ac3", "eac3", "opus", "alac", "flac"},
    "mov": {"aac", "mp3", "ac3", "eac3", "alac", "pcm_s16le", "pcm_s24le", "pcm_f32le"},
    "mkv": None,
    "webm": {"opus", "vorbis"},
}

# The new voice track: AAC where Apple players expect it, Opus elsewhere.
AUDIO_ENCODER: dict[str, tuple[str, str]] = {
    "mp4": ("aac", "256k"),
    "mov": ("aac", "256k"),
    "mkv": ("libopus", "160k"),
    "webm": ("libopus", "160k"),
}

REENCODE: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "mp4": ("H.264", "libx264", ("-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p")),
    "mov": ("H.264", "libx264", ("-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p")),
    "webm": ("VP9", "libvpx-vp9", ("-crf", "32", "-b:v", "0", "-row-mt", "1")),
}

TEXT_SUBTITLES = {"subrip", "srt", "webvtt", "mov_text", "text"}
SUBTITLE_TARGET = {"mp4": "mov_text", "mov": "mov_text", "webm": "webvtt"}

Action = Literal["copy", "convert", "drop"]


@dataclass(frozen=True)
class StreamPlan:
    index: int
    action: Action
    codec: str | None = None


@dataclass
class Plan:
    container: str
    reencode: str | None = None
    audio: list[StreamPlan] = field(default_factory=list)
    subtitles: list[StreamPlan] = field(default_factory=list)
    attachments: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def confirm_message(self) -> str | None:
        if self.reencode is None:
            return None
        return (
            f"The picture will be re-encoded to {self.reencode} for {self.container.upper()} "
            "(about as long as the video's duration on this machine)."
        )


def default_container(probe: Probe, name: str) -> str:
    """The container that matches the input. The content picks the family, the name the member."""
    ext = PurePath(name).suffix.lower().lstrip(".")
    names = set(probe.format_name.split(","))
    if "matroska" in names:
        return "webm" if ext == "webm" else "mkv"
    if "mov" in names:
        brand = probe.tags.get("major_brand", "").strip()
        return "mov" if ext == "mov" or brand == "qt" else "mp4"
    # AVI, MPEG-TS and the rest: Matroska holds whatever they carry.
    return "mkv"


def plan(probe: Probe, track: int, container: str) -> Plan:
    """Decides copy, convert, drop, or re-encode for every stream before the job starts."""
    result = Plan(container)
    video_ok = VIDEO_CODECS[container]
    if video_ok is not None and any(v.codec_name not in video_ok for v in probe.video):
        result.reencode = REENCODE[container][0]
    audio_ok = AUDIO_CODECS[container]
    for i, stream in enumerate(probe.audio):
        if i == track:
            result.audio.append(StreamPlan(stream.index, "convert", AUDIO_ENCODER[container][0]))
        elif audio_ok is None or stream.codec_name in audio_ok:
            result.audio.append(StreamPlan(stream.index, "copy"))
        else:
            result.audio.append(StreamPlan(stream.index, "convert", AUDIO_ENCODER[container][0]))
    dropped = False
    for stream in probe.subtitles:
        if container == "mkv":
            # Matroska cannot store mov_text, so that one becomes SubRip.
            if stream.codec_name == "mov_text":
                result.subtitles.append(StreamPlan(stream.index, "convert", "subrip"))
            else:
                result.subtitles.append(StreamPlan(stream.index, "copy"))
        elif stream.codec_name in TEXT_SUBTITLES:
            target = SUBTITLE_TARGET[container]
            action: Action = "copy" if stream.codec_name == target else "convert"
            result.subtitles.append(StreamPlan(stream.index, action, target))
        else:
            dropped = True
    if dropped:
        name = container.upper()
        result.notes.append(
            f"Subtitles were left out because {name} can't hold them; choose MKV to keep them."
        )
    result.attachments = container == "mkv"
    return result
