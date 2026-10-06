import errno
import json
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import soundfile as sf

from sukoon import compat, ffmpeg
from sukoon.chunk import ChunkReport
from sukoon.decode import decode, mmss
from sukoon.device import DevicePreference
from sukoon.encode import AUDIO_FORMATS, default_audio_format, encode_audio
from sukoon.errors import DISK_FULL, JobError
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


# stage, overall fraction, seconds left (known while separating and encoding)
Progress = Callable[[Stage, float, float | None], None]
ETA_SMOOTHING = 0.5
# Each output encoder's time next to the Opus preview's, on 20 minutes of speech on the
# RTX 3060 laptop. ceiling: one machine's ratios; revisit if the time left often runs over.
ENCODE_COST = {
    "aac": 7.7,
    "libopus": 1.7,
    "libmp3lame": 1.9,
    "libvorbis": 2.1,
    "flac": 0.3,
    "pcm_s24le": 0.05,
}


@dataclass(frozen=True)
class Energy:
    mixture: float
    removed: float
    voice_rms: float


PEAK_BUCKETS = 2000


def analyse(
    mixture: Path, voice: Path, buckets: int = PEAK_BUCKETS
) -> tuple[Energy, dict[str, Any]]:
    """One pass over both WAVs: the energies behind the notes, and the strip's peaks.

    Peaks are the min and max of each of `buckets` equal slices, for the voice and for what
    was removed (input minus voice), flattened as [min, max, min, max, ...].
    """
    info = sf.info(str(mixture))
    edges = np.linspace(0, info.frames, buckets + 1).round().astype(int)
    total = removed = voice_sq = 0.0
    count = 0
    lanes: dict[str, list[float]] = {"voice": [], "removed": []}
    with sf.SoundFile(str(mixture)) as m, sf.SoundFile(str(voice)) as v:
        for size in np.diff(edges):
            a = m.read(max(int(size), 1), dtype="float64", always_2d=True)
            b = v.read(max(int(size), 1), dtype="float64", always_2d=True)
            n = min(len(a), len(b))
            if n == 0:
                for lane in lanes.values():
                    lane.extend([0.0, 0.0])
                continue
            a, b = a[:n], b[:n]
            total += float(np.sum(a * a))
            removed += float(np.sum((a - b) ** 2))
            voice_sq += float(np.sum(b * b))
            count += b.size
            for name, signal in (("voice", b.mean(axis=1)), ("removed", (a - b).mean(axis=1))):
                lanes[name] += [round(float(signal.min()), 4), round(float(signal.max()), 4)]
    energy = Energy(total, removed, float(np.sqrt(voice_sq / max(count, 1))))
    return energy, {"seconds": info.frames / info.samplerate, **lanes}


def encode_preview(wav: Path, target: Path, cancelled: Callable[[], bool]) -> float:
    """A small Opus copy for the review player; returns how long the encode took."""
    started = time.monotonic()
    partial = target.with_name(f".{target.name}.part")
    ffmpeg.run(
        [
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(wav),
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            "-compression_level",
            "5",
            "-f",
            "webm",
            "-y",
            str(partial),
        ],
        float(sf.info(str(wav)).duration),
        cancelled=cancelled,
    )
    partial.replace(target)
    return time.monotonic() - started


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
    encoder = compat.AUDIO_ENCODER[fmt][0] if video_plan else AUDIO_FORMATS[fmt].encoder
    if video_plan and video_plan.reencode and not options.reencode_ok:
        raise JobError(video_plan.confirm_message or "The picture needs re-encoding.")

    def report(stage: Stage, fraction: float, eta: float | None = None) -> None:
        lo, hi = WEIGHTS[stage]
        progress(stage, lo + (hi - lo) * fraction, eta)

    stop = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)

    notes: list[str] = []
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        mixture, voice = work_dir / "mixture.wav", work_dir / "voice.wav"
        report("decoding", 0.0)
        started = time.monotonic()
        decoded = decode(source, probe, track, mixture, lambda f: report("decoding", f), cancelled)
        decode_s = time.monotonic() - started
        # The original's preview needs only the decoded input, so it runs during separation.
        original_preview = pool.submit(
            encode_preview,
            mixture,
            out_dir / "preview-original.webm",
            lambda: cancelled() or stop.is_set(),
        )
        if probe.audio[track].channels > 2:
            notes.append(NOTE_SURROUND)
        if decoded.partial:
            notes.append(
                f"The source file is damaged after {mmss(decoded.seconds)}; the output stops there."
            )
        report("separating", 0.0)
        chunk_started, per_chunk = time.monotonic(), 0.0

        def on_chunk(done: int, total: int) -> None:
            nonlocal chunk_started, per_chunk
            now = time.monotonic()
            took, chunk_started = now - chunk_started, now
            per_chunk = (
                took if not per_chunk else (ETA_SMOOTHING * took + (1 - ETA_SMOOTHING) * per_chunk)
            )
            # What follows separation: the voice's preview (timed off the original's, or
            # guessed from the decode until that is done), the analysis, and the encode.
            preview_s = (
                original_preview.result()
                if original_preview.done() and original_preview.exception() is None
                else 4 * decode_s
            )
            after = preview_s * (1 + ENCODE_COST.get(encoder, 1.0)) + 2 * decode_s
            report("separating", done / total, (total - done) * per_chunk + after)

        chunks = separate(mixture, voice, work_dir, cancelled, on_chunk)
        original_preview.result()
        energy, peaks = analyse(mixture, voice)
        (out_dir / "peaks.json").write_text(json.dumps(peaks), encoding="utf-8")
        encode_preview(voice, out_dir / "preview-clean.webm", cancelled)
        if energy.mixture > 0 and energy.removed < 0.01 * energy.mixture:
            notes.append(NOTE_NO_MUSIC)
        if energy.voice_rms < 10 ** (-50 / 20):
            notes.append(NOTE_NO_VOICE)
        if chunks.cpu_fallbacks:
            notes.append(NOTE_CPU)
        report("encoding", 0.0)
        encode_started = time.monotonic()

        def encoding(fraction: float) -> None:
            # ffmpeg moves steadily, so the time so far scales up to the time left.
            elapsed = time.monotonic() - encode_started
            report("encoding", fraction, elapsed / fraction - elapsed if fraction > 0.01 else None)

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
                encoding,
                cancelled,
            )
        else:
            encode_audio(voice, source, probe, track, fmt, out, encoding, cancelled)
        return Result(output=out.name, format=fmt, notes=notes, seconds=decoded.seconds)
    except BaseException as exc:
        # The output folder is this job's alone; nothing half made may stay in it.
        stop.set()
        pool.shutdown(wait=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            raise JobError(DISK_FULL) from exc
        raise
    finally:
        stop.set()
        pool.shutdown(wait=True)
        shutil.rmtree(work_dir, ignore_errors=True)
