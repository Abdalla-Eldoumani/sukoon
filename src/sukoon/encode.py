import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sukoon import ffmpeg
from sukoon.probe import Probe

MAX_RATE = 48000


@dataclass(frozen=True)
class AudioFormat:
    ext: str
    muxer: str
    encoder: str
    codec_args: tuple[str, ...]
    cover: bool = False
    fixed_rate: int | None = None


# High quality settings, since the source is often lossy already.
AUDIO_FORMATS: dict[str, AudioFormat] = {
    "mp3": AudioFormat("mp3", "mp3", "libmp3lame", ("-c:a", "libmp3lame", "-q:a", "0"), True),
    "m4a": AudioFormat("m4a", "ipod", "aac", ("-c:a", "aac", "-b:a", "256k"), True),
    "wav": AudioFormat("wav", "wav", "pcm_s24le", ("-c:a", "pcm_s24le")),
    "flac": AudioFormat(
        "flac",
        "flac",
        "flac",
        ("-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"),
        True,
    ),
    "opus": AudioFormat(
        "opus", "opus", "libopus", ("-c:a", "libopus", "-b:a", "160k"), fixed_rate=48000
    ),
    "ogg": AudioFormat("ogg", "ogg", "libvorbis", ("-c:a", "libvorbis", "-q:a", "6")),
}

LOSSLESS_CODECS = {"flac", "alac", "wavpack", "ape", "tta", "truehd", "mlp"}


def default_audio_format(probe: Probe) -> str:
    """The output format that matches what came in, for an audio-only file."""
    names = set(probe.format_name.split(","))
    codec = probe.audio[0].codec_name
    if "mp3" in names or codec == "mp3":
        return "mp3"
    if "wav" in names or codec.startswith("pcm_"):
        return "wav"
    if codec == "flac" or codec in LOSSLESS_CODECS:
        return "flac"
    if codec == "opus":
        return "opus"
    if codec == "vorbis":
        return "ogg"
    return "m4a"


def output_rate(fmt: AudioFormat, source_rate: int) -> int:
    return fmt.fixed_rate or min(source_rate or MAX_RATE, MAX_RATE)


def encode_audio(
    voice_wav: Path,
    source: Path,
    probe: Probe,
    track: int,
    fmt_name: str,
    out_path: Path,
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
) -> None:
    """Writes the voice in the chosen format with the source's tags and cover art.

    The file appears under its final name only once complete, so a half-written output never
    looks finished.
    """
    fmt = AUDIO_FORMATS[fmt_name]
    stream = probe.audio[track]
    args = [
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(voice_wav),
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(source),
        "-map",
        "0:a",
        "-map_metadata",
        "1",
        "-map_chapters",
        "-1",
        *fmt.codec_args,
        "-ar",
        str(output_rate(fmt, stream.sample_rate)),
        "-ac",
        str(min(stream.channels or 2, 2)),
    ]
    if fmt.cover and probe.covers:
        args += [
            "-map",
            f"1:{probe.covers[0].index}",
            "-c:v",
            "copy",
            "-disposition:v:0",
            "attached_pic",
        ]
    if fmt.muxer == "mp3":
        args += ["-id3v2_version", "3"]
    partial = out_path.with_name(f".{out_path.name}.part")
    args += ["-f", fmt.muxer, "-y", str(partial)]
    try:
        ffmpeg.run(args, probe.duration, on_progress, cancelled)
        os.replace(partial, out_path)
    finally:
        partial.unlink(missing_ok=True)
