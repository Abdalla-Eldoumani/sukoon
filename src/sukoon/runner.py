import functools
import logging
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sukoon import pipeline
from sukoon.errors import Canceled, JobError
from sukoon.models import Preset
from sukoon.pipeline import Options
from sukoon.probe import Probe
from sukoon.settings import Settings
from sukoon.store import Store
from sukoon.worker import Worker

log = logging.getLogger("sukoon")

WAITING = {"queued", "waiting_model", "awaiting_track", "awaiting_confirm"}


def source_path(settings: Settings, job_id: str) -> Path:
    folder = settings.job_path("uploads", job_id)
    return next(folder.glob("source*"))


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
        self.thread.start()

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

        def progress(stage: str, fraction: float, done: int, total: int) -> None:
            nonlocal current_stage, shown
            if stage != current_stage:
                self.store.transition(job_id, stage, stage=stage, progress=fraction)
                current_stage, shown = stage, fraction
            elif fraction - shown >= 0.005 or fraction == 1.0:
                self.store.update(job_id, progress=fraction)
                shown = fraction

        try:
            result = pipeline.run(
                source_path(self.settings, job_id),
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
            self.store.transition(job_id, "canceled", eta=None)
        except JobError as exc:
            shutil.rmtree(out_dir, ignore_errors=True)
            self.store.transition(job_id, "failed", error=str(exc), eta=None)
        except Exception as exc:
            log.exception("job %s failed", job_id)
            shutil.rmtree(out_dir, ignore_errors=True)
            self.store.transition(job_id, "failed", error=f"Something went wrong: {exc}", eta=None)
        else:
            self.store.transition(job_id, "done", result=result.to_json(), progress=1.0, eta=None)
