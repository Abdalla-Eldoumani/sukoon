from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from sukoon.engine import Engine, OutOfMemory
from sukoon.errors import Canceled

CHUNK_S = 60
OVERLAP_S = 4
MIN_S = 10


@dataclass(frozen=True)
class ChunkReport:
    chunks: int
    cpu_fallbacks: int


def windows(frames: int, rate: int) -> list[tuple[int, int]]:
    """(start, length) of each chunk; neighbours share OVERLAP_S seconds."""
    size, hop = CHUNK_S * rate, (CHUNK_S - OVERLAP_S) * rate
    out = []
    start = 0
    while start + size < frames:
        out.append((start, size))
        start += hop
    out.append((start, frames - start))
    return out


def wav_format(frames: int, channels: int) -> str:
    # Plain WAV stops at 4 GB; a six-hour file needs RF64.
    return "RF64" if frames * channels * 4 > 4_000_000_000 else "WAV"


def separate_chunked(
    engine: Engine,
    mixture: Path,
    voice: Path,
    scratch: Path,
    cancelled: Callable[[], bool],
    on_chunk: Callable[[int, int], None],
) -> ChunkReport:
    """Separates a long WAV window by window so memory use does not grow with its length."""
    info = sf.info(str(mixture))
    rate, channels, frames = info.samplerate, info.channels, info.frames
    plan = windows(frames, rate)
    overlap = OVERLAP_S * rate
    fade_in = np.linspace(0.0, 1.0, overlap, endpoint=False, dtype=np.float32)[:, None]
    tail: np.ndarray | None = None
    fallbacks = 0
    chunk_in, chunk_out = scratch / "chunk-in.wav", scratch / "chunk-out.wav"
    with (
        sf.SoundFile(str(mixture)) as src,
        sf.SoundFile(
            str(voice), "w", rate, channels, "FLOAT", format=wav_format(frames, channels)
        ) as dst,
    ):
        for i, (start, length) in enumerate(plan):
            if cancelled():
                raise Canceled
            src.seek(start)
            block = src.read(length, dtype="float32", always_2d=True)
            padded = max(length, MIN_S * rate)
            if padded > length:
                block = np.concatenate([block, np.zeros((padded - length, channels), np.float32)])
            sf.write(str(chunk_in), block, rate, subtype="FLOAT")
            try:
                engine.separate(chunk_in, chunk_out)
            except OutOfMemory:
                fallbacks += 1
                engine.separate(chunk_in, chunk_out, on_cpu=True)
            out = sf.read(str(chunk_out), dtype="float32", always_2d=True)[0][:length]
            if len(out) < length:
                out = np.concatenate([out, np.zeros((length - len(out), channels), np.float32)])
            if tail is not None:
                out[:overlap] = tail * (1 - fade_in) + out[:overlap] * fade_in
            last = i == len(plan) - 1
            dst.write(out if last else out[: length - overlap])
            tail = None if last else out[length - overlap :].copy()
            on_chunk(i + 1, len(plan))
    chunk_in.unlink(missing_ok=True)
    chunk_out.unlink(missing_ok=True)
    return ChunkReport(len(plan), fallbacks)
