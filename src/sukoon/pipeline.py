import errno
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import soundfile as sf

from sukoon import compat
from sukoon.chunk import ChunkReport
from sukoon.decode import decode, mmss
from sukoon.device import DevicePreference
from sukoon.encode import AUDIO_FORMATS, default_audio_format, encode_audio
from sukoon.errors import JobError
from sukoon.models import Preset
from sukoon.mux import mux_video
from sukoon.probe import Probe

Stage = Literal["decoding", "separating", "encoding"]
# Share of the bar each stage fills; separation is nearly all of the wait.
WEIGHTS: dict[Stage, tuple[float, float]] = {
    "decoding": (0.0, 0.05),
    "separating": (0.05, 0.95),
    "encoding": (0.95, 1.0),
}

NOTE_SURROUND = "Surround was mixed down to stereo."
NOTE_NO_MUSIC = "There was almost no music in this file."
NOTE_NO_VOICE = "No voices were found; the output is nearly silent."
NOTE_CPU = "Part of this ran on the CPU because the GPU ran out of memory."
DISK_FULL = "The disk is full."


class Separator(Protocol):
    def __call__(
        self,
        mixture: Path,
        voice: Path,
        scratch: Path,
        cancelled: Callable[[], bool],
        on_chunk: Callable[[int, int], None],
    ) -> ChunkReport: ...


@dataclass(frozen=True)
class Options:
    preset: Preset = "best"
    device: DevicePreference = "auto"
    format: str | None = None
    track: int | None = None
    reencode_ok: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Result:
    output: str
    format: str
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


Progress = Callable[[Stage, float, int, int], None]


@dataclass(frozen=True)
class Energy:
    mixture: float
    removed: float
    voice_rms: float


def measure(mixture: Path, voice: Path, block: int = 1 << 20) -> Energy:
    """Energy of the input, of what was removed, and the voice's RMS, read in blocks."""
    total = removed = voice_sq = 0.0
    count = 0
    with sf.SoundFile(str(mixture)) as m, sf.SoundFile(str(voice)) as v:
        while True:
            a = m.read(block, dtype="float64", always_2d=True)
            b = v.read(block, dtype="float64", always_2d=True)
            n = min(len(a), len(b))
            if n == 0:
                break
            a, b = a[:n], b[:n]
            total += float(np.sum(a * a))
            removed += float(np.sum((a - b) ** 2))
            voice_sq += float(np.sum(b * b))
            count += b.size
    return Energy(total, removed, float(np.sqrt(voice_sq / max(count, 1))))


def output_format(probe: Probe, options: Options, source_name: str) -> str:
    """The chosen format, or the one matching the input; checked against what can be written."""
    if options.format:
        fmt = options.format
    elif probe.kind == "video":
        fmt = compat.default_container(probe, source_name)
    else:
        fmt = default_audio_format(probe)
    if fmt in compat.VIDEO_CONTAINERS and probe.kind != "video":
        raise JobError(f"This file has no picture, so it can't become {fmt.upper()} video.")
    if fmt not in AUDIO_FORMATS and fmt not in compat.VIDEO_CONTAINERS:
        raise JobError(f"{fmt.upper()} isn't an output format sukoon can write.")
    return fmt


def extension(fmt: str) -> str:
    return AUDIO_FORMATS[fmt].ext if fmt in AUDIO_FORMATS else fmt


def run(
    source: Path,
    probe: Probe,
    options: Options,
    separate: Separator,
    cancelled: Callable[[], bool],
    progress: Progress,
    work_dir: Path,
    out_dir: Path,
) -> Result:
    """Probe result in, finished file out: decode, separate, encode, with notes for the user."""
    track = options.track if options.track is not None else probe.default_audio()
    if not 0 <= track < len(probe.audio):
        raise JobError("That audio track doesn't exist in this file.")
    fmt = output_format(probe, options, source.name)
    video_plan = compat.plan(probe, track, fmt) if fmt in compat.VIDEO_CONTAINERS else None
    if video_plan and video_plan.reencode and not options.reencode_ok:
        raise JobError(video_plan.confirm_message or "The picture needs re-encoding.")

    def report(stage: Stage, fraction: float, done: int = 0, total: int = 0) -> None:
        lo, hi = WEIGHTS[stage]
        progress(stage, lo + (hi - lo) * fraction, done, total)

    notes: list[str] = []
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        mixture, voice = work_dir / "mixture.wav", work_dir / "voice.wav"
        report("decoding", 0.0)
        decoded = decode(source, probe, track, mixture, lambda f: report("decoding", f), cancelled)
        if probe.audio[track].channels > 2:
            notes.append(NOTE_SURROUND)
        if decoded.partial:
            notes.append(
                f"The source file is damaged after {mmss(decoded.seconds)}; the output stops there."
            )
        report("separating", 0.0)
        chunks = separate(
            mixture,
            voice,
            work_dir,
            cancelled,
            lambda d, t: report("separating", d / t, d, t),
        )
        energy = measure(mixture, voice)
        if energy.mixture > 0 and energy.removed < 0.01 * energy.mixture:
            notes.append(NOTE_NO_MUSIC)
        if energy.voice_rms < 10 ** (-50 / 20):
            notes.append(NOTE_NO_VOICE)
        if chunks.cpu_fallbacks:
            notes.append(NOTE_CPU)
        report("encoding", 0.0)
        out = out_dir / f"output.{extension(fmt)}"
        if video_plan is not None:
            notes.extend(video_plan.notes)
            mux_video(
                voice,
                source,
                probe,
                track,
                video_plan,
                out,
                lambda f: report("encoding", f),
                cancelled,
            )
        else:
            encode_audio(
                voice, source, probe, track, fmt, out, lambda f: report("encoding", f), cancelled
            )
        return Result(output=out.name, format=fmt, notes=notes, seconds=decoded.seconds)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise JobError(DISK_FULL) from exc
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
