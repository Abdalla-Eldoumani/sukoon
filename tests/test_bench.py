import re

import soundfile as sf

from sukoon.bench import bench, make_clip
from sukoon.engine import FakeEngine


def test_clip_is_thirty_seconds_of_stereo(tmp_path):
    info = sf.info(str(make_clip(tmp_path / "clip.wav")))
    assert (info.samplerate, info.channels, info.frames) == (44100, 2, 30 * 44100)


def test_bench_reports_three_runs_and_their_median(tmp_path):
    lines = []
    # One chunk of 30 s taking about half a second: roughly 60 times real time.
    factor = bench(FakeEngine(delay=0.5), "fast", "cpu", out=lines.append)
    runs = [line for line in lines if line.startswith("run ")]
    assert len(runs) == 3
    assert lines[-1] == f"fast on CPU: {factor:.2f}x real time (median of 3)"
    speeds = sorted(float(re.search(r"\(([\d.]+)x\)", r).group(1)) for r in runs)
    assert abs(factor - speeds[1]) < 0.01
    assert 20 < factor < 61
