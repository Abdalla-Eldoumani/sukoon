from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from sukoon import ffmpeg
from sukoon.errors import JobError
from sukoon.probe import Probe

RATE = 44100


@dataclass(frozen=True)
class Decoded:
    frames: int
    seconds: float
    expected: float

    @property
    def partial(self) -> bool:
        return self.seconds < self.expected - max(0.5, self.expected * 0.02)


def mmss(seconds: float) -> str:
    whole = int(seconds)
    return (
        f"{whole // 60:02d}:{whole % 60:02d}"
        if whole < 3600
        else (f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}")
    )


def decode(
    source: Path,
    probe: Probe,
    track: int,
    out_wav: Path,
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
) -> Decoded:
    """Decodes one audio track to 44.1 kHz stereo float, the form the models expect."""
    stream = probe.audio[track]
    expected = stream.duration or probe.duration
    try:
        ffmpeg.run(
            [
                "-copyts",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                f"0:a:{track}",
                "-vn",
                "-ac",
                "2",
                # Sample 0 of the WAV is the track's start time on the source's own clock,
                # whatever the codec does with priming; the mux relies on that.
                "-af",
                f"aresample={RATE}:async=1:first_pts={round(stream.start_time * RATE)}",
                "-c:a",
                "pcm_f32le",
                "-rf64",
                "auto",
                "-f",
                "wav",
                "-y",
                str(out_wav),
            ],
            expected,
            on_progress,
            cancelled,
        )
    except ffmpeg.FfmpegTimeout:
        raise
    except ffmpeg.FfmpegError:
        # A damaged file can make ffmpeg exit with an error after decoding most of it.
        if not out_wav.exists():
            raise
    try:
        frames = sf.info(str(out_wav)).frames
    except RuntimeError:
        frames = 0
    result = Decoded(frames, frames / RATE, expected)
    if result.seconds < expected * 0.5:
        if frames == 0:
            raise JobError("The audio in this file couldn't be decoded.")
        raise JobError(
            f"The source file is damaged after {mmss(result.seconds)}, too early to be useful."
        )
    return result
