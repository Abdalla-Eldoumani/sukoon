import functools
import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sukoon import pipeline
from sukoon.errors import Canceled, JobError
from sukoon.models import Preset
from sukoon.pipeline import Options
from sukoon.probe import Probe
from sukoon.settings import Settings
from sukoon.store import FINISHED, RUNNING, STOPPED, Store
from sukoon.worker import Worker

log = logging.getLogger("sukoon")

WAITING = {"checking", "queued", "waiting_model", "awaiting_track", "awaiting_confirm"}
STALE_PART_S = 3600
ETA_SMOOTHING = 0.5


class RunnerError(Exception):
    """A request the job's current state does not allow; the message is shown as written."""


def source_path(settings: Settings, job_id: str) -> Path | None:
    folder = settings.job_path("uploads", job_id)
    return next(folder.glob("source*"), None) if folder.is_dir() else None


class Runner:
    """One thread that runs queued jobs one at a time, in the order they arrived."""

    def __init__(
        self,
        settings: Settings,
        store: Store,
        worker: Worker,
        model_ready: Callable[[Preset], bool],
    ) -> None:
        self.settings = settings
        self.store = store
        self.worker = worker
        self.model_ready = model_ready
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.cancels: set[str] = set()
        self.current: str | None = None
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._loop, name="sukoon-runner", daemon=True)

    def start(self) -> None:
        self.recover()
        self.thread.start()

    def recover(self) -> None:
        """After a stop or a crash: running jobs become interrupted and leftovers are swept."""
        for job in self.store.list():
            if job["state"] not in RUNNING:
                continue
            if source_path(self.settings, job["id"]) is None:
                shutil.rmtree(self.settings.job_path("uploads", job["id"]), ignore_errors=True)
                self.store.transition(
                    job["id"], "failed", retryable=False, error="The upload didn't finish."
                )
            else:
                self.store.transition(job["id"], "interrupted", eta=None)
        # Nothing runs yet, so every scratch folder is left over from before.
        for folder in self.settings.area("work").iterdir():
            shutil.rmtree(folder, ignore_errors=True)
        cutoff = time.time() - STALE_PART_S
        for area in ("uploads", "models"):
            for part in self.settings.area(area).rglob("*.part"):
                if part.stat().st_mtime < cutoff:
                    part.unlink(missing_ok=True)

    def retry(self, job_id: str, target: str = "queued") -> None:
        """Back to the queue, or to the question that was still open when it stopped."""
        with self.lock:
            job = self.store.get(job_id)
            if job["state"] not in STOPPED:
                raise RunnerError("Only a failed, canceled, or interrupted job can be retried.")
            if not job["retryable"] or source_path(self.settings, job_id) is None:
                raise RunnerError("This file can't be retried; add it again.")
            shutil.rmtree(self.settings.job_path("outputs", job_id), ignore_errors=True)
            self.store.transition(
                job_id, target, progress=0.0, eta=None, error=None, result=None, stage=None
            )
        self.wake.set()

    def delete(self, job_id: str) -> None:
        """Removes a job and every file it made. A running job has to be canceled first."""
        with self.lock:
            job = self.store.get(job_id)
            if job["state"] in RUNNING - {"checking"} or job_id == self.current:
                raise RunnerError("Cancel this job before deleting it.")
            for area in ("uploads", "work", "outputs"):
                shutil.rmtree(self.settings.job_path(area, job_id), ignore_errors=True)
            self.store.delete(job_id)

    def clear_finished(self) -> int:
        finished = [j["id"] for j in self.store.list() if j["state"] in FINISHED]
        for job_id in finished:
            self.delete(job_id)
        return len(finished)

    def stop(self) -> None:
        self.stopping.set()
        with self.lock:
            if self.current:
                self.cancels.add(self.current)
        self.wake.set()
        self.thread.join(timeout=30)
        self.worker.stop()

    def notify(self) -> None:
        self.wake.set()

    def models_changed(self) -> None:
        # Under the lock, so a job cannot be parked as waiting just after this pass.
        with self.lock:
            for job in self.store.list():
                if job["state"] == "waiting_model" and self.model_ready(job["options"]["preset"]):
                    self.store.transition(job["id"], "queued")
        self.wake.set()

    def cancel(self, job_id: str) -> None:
        """Waiting jobs stop at once; a running job stops at the next chunk or ffmpeg kill."""
        with self.lock:
            job = self.store.get(job_id)
            if job["state"] in WAITING:
                self.store.transition(job_id, "canceled")
            elif job_id == self.current:
                self.cancels.add(job_id)

    def _next(self) -> dict[str, Any] | None:
        while job := self.store.next_queued():
            if self.model_ready(job["options"]["preset"]):
                return job
            self.store.transition(job["id"], "waiting_model")
        return None

    def _loop(self) -> None:
        while not self.stopping.is_set():
            with self.lock:
                job = self._next()
                if job is not None:
                    self.current = job["id"]
                    self.store.transition(
                        job["id"],
                        "decoding",
                        stage="decoding",
                        progress=0.0,
                        error=None,
                        result=None,
                    )
            if job is None:
                self.wake.wait(1.0)
                self.wake.clear()
                continue
            try:
                self._run(job)
            finally:
                with self.lock:
                    self.current = None
                    self.cancels.discard(job["id"])

    def _run(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        options = Options(**job["options"])
        out_dir = self.settings.job_path("outputs", job_id)
        current_stage, shown = "decoding", 0.0
        chunk_started, per_chunk = time.monotonic(), 0.0

        def progress(stage: str, fraction: float, done: int, total: int) -> None:
            nonlocal current_stage, shown, chunk_started, per_chunk
            now = time.monotonic()
            if stage != current_stage:
                # The estimate covers separation; encoding is short and has none.
                self.store.transition(job_id, stage, stage=stage, progress=fraction, eta=None)
                current_stage, shown, chunk_started = stage, fraction, now
            elif stage == "separating" and done:
                # Smoothed seconds per chunk; the estimate shows from the first finished chunk.
                took = now - chunk_started
                per_chunk = (
                    took
                    if not per_chunk
                    else (ETA_SMOOTHING * took + (1 - ETA_SMOOTHING) * per_chunk)
                )
                chunk_started = now
                self.store.update(job_id, progress=fraction, eta=(total - done) * per_chunk)
                shown = fraction
            elif fraction - shown >= 0.005 or fraction == 1.0:
                self.store.update(job_id, progress=fraction)
                shown = fraction

        source = source_path(self.settings, job_id)
        if source is None:
            self.store.transition(
                job_id, "failed", error="The uploaded file is missing.", retryable=False
            )
            return
        try:
            result = pipeline.run(
                source,
                Probe.from_json(job["probe"]),
                options,
                functools.partial(
                    self.worker.separate, preset=options.preset, device=options.device
                ),
                lambda: job_id in self.cancels,
                progress,
                self.settings.job_path("work", job_id),
                out_dir,
            )
        except Canceled:
            shutil.rmtree(out_dir, ignore_errors=True)
            # Stopping the app is not the user's cancel, so the job comes back with Retry.
            state = "interrupted" if self.stopping.is_set() else "canceled"
            self.store.transition(job_id, state, eta=None)
        except JobError as exc:
            shutil.rmtree(out_dir, ignore_errors=True)
            self.store.transition(job_id, "failed", error=str(exc), eta=None)
        except Exception as exc:
            log.exception("job %s failed", job_id)
            shutil.rmtree(out_dir, ignore_errors=True)
            self.store.transition(job_id, "failed", error=f"Something went wrong: {exc}", eta=None)
        else:
            self.store.transition(job_id, "done", result=result.to_json(), progress=1.0, eta=None)
