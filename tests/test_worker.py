import hashlib
import time

import numpy as np
import pytest
import soundfile as sf

from sukoon.errors import Canceled, JobError
from sukoon.models import CHECKSUM_MESSAGE, ModelFile
from sukoon.worker import CRASHED, STALLED, Worker, WorkerConfig

SR = 44100


@pytest.fixture
def job(tmp_path):
    """A scratch folder named like a job, holding a 70-second mixture (two chunks)."""
    scratch = tmp_path / "work" / "8a6f0c2e-2a8b-4f3e-9d61-2b1f4c9e7a10"
    scratch.mkdir(parents=True)
    data = (np.random.default_rng(0).standard_normal((70 * SR, 2)) * 0.1).astype(np.float32)
    sf.write(scratch / "mixture.wav", data, SR, subtype="FLOAT")
    return scratch, data


def run(worker, scratch, cancelled=lambda: False, seen=None):
    seen = [] if seen is None else seen
    return worker.separate(
        scratch / "mixture.wav",
        scratch / "voice.wav",
        scratch,
        cancelled,
        lambda d, t: seen.append((d, t)),
        preset="fast",
        device="cpu",
    )


@pytest.fixture
def make_worker(tmp_path):
    workers = []

    def make(**fake):
        w = Worker(WorkerConfig(models_dir=tmp_path / "models", fake=fake))
        workers.append(w)
        return w

    yield make
    for w in workers:
        w.stop()


def test_separates_in_the_child_and_reports_chunks(job, make_worker):
    scratch, data = job
    seen = []
    report = run(make_worker(), scratch, seen=seen)
    assert report.chunks == 2
    assert seen == [(1, 2), (2, 2)]
    voice, _ = sf.read(scratch / "voice.wav", dtype="float32")
    np.testing.assert_allclose(voice, data * 0.5, atol=1e-6)


def test_model_stays_loaded_between_jobs(job, make_worker):
    scratch, _ = job
    worker = make_worker()
    run(worker, scratch)
    pid = worker.process.pid
    run(worker, scratch)
    assert worker.process.pid == pid


def test_crash_fails_the_job_and_the_next_job_succeeds(job, make_worker):
    scratch, _ = job
    worker = make_worker(fail="exit", fail_on=3)
    run(worker, scratch)  # calls 1 and 2
    with pytest.raises(JobError, match=CRASHED):
        run(worker, scratch)  # call 3 exits the process
    assert run(worker, scratch).chunks == 2


def test_out_of_memory_falls_back_to_cpu_for_that_chunk(job, make_worker):
    scratch, data = job
    report = run(make_worker(fail="oom", fail_on=1), scratch)
    assert report.cpu_fallbacks == 1
    voice, _ = sf.read(scratch / "voice.wav", dtype="float32")
    np.testing.assert_allclose(voice, data * 0.5, atol=1e-6)


def test_engine_error_is_reported_as_a_job_error(job, make_worker):
    scratch, _ = job
    with pytest.raises(JobError, match="fake engine failure"):
        run(make_worker(fail="raise"), scratch)


def test_cancel_lands_within_one_chunk(job, make_worker):
    scratch, _ = job
    longer = (np.random.default_rng(1).standard_normal((180 * SR, 2)) * 0.1).astype(np.float32)
    sf.write(scratch / "mixture.wav", longer, SR, subtype="FLOAT")
    seen = []
    started = time.monotonic()
    with pytest.raises(Canceled):
        run(make_worker(delay=1.0), scratch, cancelled=lambda: bool(seen), seen=seen)
    # The chunk already under way may finish; the one after it never starts.
    assert len(seen) <= 2
    assert time.monotonic() - started < 10


def test_tampered_model_fails_the_job_with_the_checksum_message(job, tmp_path):
    scratch, _ = job
    models = tmp_path / "models"
    models.mkdir()
    body = b"weights" * 1000
    (models / "UVR-MDX-NET-Voc_FT.onnx").write_bytes(body[:-1] + b"X")
    files = (
        ModelFile(
            "fast",
            "UVR-MDX-NET-Voc_FT.onnx",
            "https://example.invalid/m",
            len(body),
            hashlib.sha256(body).hexdigest(),
        ),
    )
    worker = Worker(WorkerConfig(models_dir=models, model_files=files))
    try:
        with pytest.raises(JobError, match=CHECKSUM_MESSAGE):
            run(worker, scratch)
    finally:
        worker.stop()
    assert not (models / "UVR-MDX-NET-Voc_FT.onnx").exists()


def test_a_chunk_that_never_finishes_fails_the_job_and_the_next_job_succeeds(job, tmp_path):
    scratch, _ = job
    config = WorkerConfig(models_dir=tmp_path, fake={"fail": "hang", "fail_on": 3})
    worker = Worker(config, stall_s=2)
    try:
        run(worker, scratch)  # calls 1 and 2
        started = time.monotonic()
        with pytest.raises(JobError, match=STALLED):
            run(worker, scratch)  # call 3 never returns
        assert time.monotonic() - started < 10
        assert run(worker, scratch).chunks == 2
    finally:
        worker.stop()
