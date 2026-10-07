import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from sukoon.separation.chunk import separate_chunked
from sukoon.separation.device import DevicePreference, detect
from sukoon.separation.engine import Engine
from sukoon.separation.models import Preset

RATE = 44100
SECONDS = 30
RUNS = 3


def make_clip(path: Path, seconds: int = SECONDS) -> Path:
    """Thirty seconds of chords and noise bursts; the model's speed does not depend on content."""
    t = np.arange(seconds * RATE) / RATE
    chords = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 275.0, 330.0)) / 3
    bursts = np.random.default_rng(0).standard_normal(t.size) * (np.sin(2 * np.pi * 2 * t) > 0.9)
    mono = 0.4 * chords + 0.1 * bursts
    sf.write(path, np.stack([mono, mono], axis=1).astype(np.float32), RATE, subtype="FLOAT")
    return path


def bench(
    engine: Engine,
    preset: Preset,
    device: DevicePreference,
    clip: Path | None = None,
    out: Callable[[str], None] = print,
) -> float:
    """Separates the clip RUNS times and returns the median real-time factor (audio s per s)."""
    with tempfile.TemporaryDirectory(prefix="sukoon-bench-") as name:
        scratch = Path(name)
        mixture = clip or make_clip(scratch / "clip.wav")
        seconds = float(sf.info(str(mixture)).duration)
        started = time.monotonic()
        engine.prepare(preset, device)
        out(f"model load: {time.monotonic() - started:.1f} s")
        factors = []
        for run in range(1, RUNS + 1):
            started = time.monotonic()
            separate_chunked(
                engine, mixture, scratch / "voice.wav", scratch, lambda: False, lambda d, t: None
            )
            took = time.monotonic() - started
            factors.append(seconds / took)
            out(f"run {run}: {took:.1f} s for {seconds:.0f} s of audio ({seconds / took:.2f}x)")
    median = float(statistics.median(factors))
    label = "CPU" if device == "cpu" else detect(device).label
    out(f"{preset} on {label}: {median:.2f}x real time (median of {RUNS})")
    return median
