import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from sukoon import tools

Kind = Literal["audio", "video"]

UNREADABLE = "This file isn't audio or video sukoon can read."
PLAYLIST = "This is a playlist, not a media file."
NO_SOUND = "This video has no sound track, so there is nothing to clean."

# Demuxers that open other files or network addresses.
DENIED_FORMATS = {"hls", "concat", "sdp", "rtp", "rtsp", "tee", "image2", "image2pipe"}
# Playlists are refused on sight, before ffprobe gets a chance to follow them.
PLAYLIST_MAGIC = (b"#EXTM3U", b"ffconcat", b"v=0\r\n", b"v=0\n", b"[playlist]")


class Rejected(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Stream:
    index: int
    codec_type: str
    codec_name: str
    channels: int = 0
    sample_rate: int = 0
    start_time: float = 0.0
    duration: float = 0.0
    language: str | None = None
    title: str | None = None
    default: bool = False
    attached_pic: bool = False
    frames: int | None = None
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class Probe:
    format_name: str
    duration: float
    size: int
    streams: list[Stream] = field(default_factory=list)
    chapters: int = 0
    tags: dict[str, str] = field(default_factory=dict)
    # ffprobe guessed the duration from the bitrate (raw AAC, for one), so it is approximate.
    estimated: bool = False

    @property
    def audio(self) -> list[Stream]:
        return [s for s in self.streams if s.codec_type == "audio"]

    @property
    def video(self) -> list[Stream]:
        """Real picture streams; cover art and single still frames do not count."""
        return [
            s
            for s in self.streams
            if s.codec_type == "video" and not s.attached_pic and s.frames != 1
        ]

    @property
    def covers(self) -> list[Stream]:
        return [s for s in self.streams if s.codec_type == "video" and s.attached_pic]

    @property
    def subtitles(self) -> list[Stream]:
        return [s for s in self.streams if s.codec_type == "subtitle"]

    @property
    def kind(self) -> Kind:
        return "video" if self.video else "audio"

    def default_audio(self) -> int:
        """Position of the default audio track among the audio tracks, else the first."""
        for i, s in enumerate(self.audio):
            if s.default:
                return i
        return 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Probe":
        streams = [Stream(**s) for s in data.get("streams", [])]
        return cls(**{**data, "streams": streams})


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse(raw: dict[str, Any], estimated: bool = False) -> Probe:
    fmt = raw.get("format", {})
    streams = []
    for s in raw.get("streams", []):
        tags = {k.lower(): v for k, v in s.get("tags", {}).items()}
        disp = s.get("disposition", {})
        frames = s.get("nb_frames") or s.get("nb_read_frames")
        streams.append(
            Stream(
                index=_int(s.get("index")),
                codec_type=str(s.get("codec_type", "")),
                codec_name=str(s.get("codec_name", "")),
                channels=_int(s.get("channels")),
                sample_rate=_int(s.get("sample_rate")),
                start_time=_float(s.get("start_time")),
                duration=_float(s.get("duration")),
                language=tags.get("language"),
                title=tags.get("title"),
                default=bool(disp.get("default")),
                attached_pic=bool(disp.get("attached_pic")),
                frames=_int(frames) if frames not in (None, "N/A") else None,
                width=_int(s.get("width")),
                height=_int(s.get("height")),
            )
        )
    duration = _float(fmt.get("duration"), default=-1.0)
    if duration < 0 and streams:
        duration = max(
            (_float(s.get("duration"), -1.0) for s in raw.get("streams", [])), default=-1.0
        )
    return Probe(
        format_name=str(fmt.get("format_name", "")),
        duration=duration,
        size=_int(fmt.get("size")),
        streams=streams,
        chapters=len(raw.get("chapters", [])),
        tags={str(k): str(v) for k, v in fmt.get("tags", {}).items()},
        estimated=estimated,
    )


def run_ffprobe(path: Path, timeout: float = 60) -> tuple[dict[str, Any], bool]:
    """The parsed JSON, and whether the duration in it is a guess from the bitrate."""
    exe = tools.ffprobe_path()
    if exe is None:
        raise RuntimeError("ffprobe was not found")
    out = subprocess.run(
        [
            exe,
            "-v",
            "warning",
            "-protocol_whitelist",
            "file,pipe",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-i",
            str(path),
        ],
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if out.returncode != 0:
        raise Rejected(UNREADABLE)
    try:
        data: dict[str, Any] = json.loads(out.stdout)
    except ValueError as exc:
        raise Rejected(UNREADABLE) from exc
    return data, b"Estimating duration from bitrate" in out.stderr


def is_denied(format_name: str) -> bool:
    names = {n.strip() for n in format_name.split(",")}
    return bool(names & DENIED_FORMATS) or any(n.endswith("_pipe") for n in names)


def probe(path: Path, max_duration: float | None = None) -> Probe:
    """Reads a file's streams and decides whether sukoon can work on it; raises Rejected."""
    if path.stat().st_size == 0:
        raise Rejected(UNREADABLE)
    with path.open("rb") as f:
        head = f.read(64).lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(PLAYLIST_MAGIC):
        raise Rejected(PLAYLIST)
    result = parse(*run_ffprobe(path))
    if is_denied(result.format_name):
        raise Rejected(PLAYLIST)
    if not result.audio:
        raise Rejected(NO_SOUND if result.video else UNREADABLE)
    if result.duration <= 0:
        raise Rejected(UNREADABLE)
    if max_duration is not None and result.duration > max_duration:
        hours = max_duration / 3600
        raise Rejected(f"This file is longer than {hours:g} hours, which is sukoon's limit.")
    return result
