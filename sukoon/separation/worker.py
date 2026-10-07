import errno
import multiprocessing as mp
import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.context import SpawnProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from sukoon.chunk import ChunkReport, separate_chunked
from sukoon.device import DevicePreference
from sukoon.engine import AudioSeparatorEngine, Engine, FakeEngine
from sukoon.errors import DISK_FULL, Canceled, JobError
from sukoon.models import MODEL_FILES, ModelChecksumError, ModelFile, Preset

CRASHED = "The separation engine stopped unexpectedly."
CANCEL_GRACE_S = 20.0
# One chunk on the slowest machine measured takes about five minutes; past this it is stuck.
STALL_S = 1800.0
STALLED = "The separation engine stopped responding."


@dataclass(frozen=True)
class WorkerConfig:
    """Everything the child needs, picklable for the spawn start method."""

    models_dir: Path
    fake: dict[str, Any] | None = None
    model_files: tuple[ModelFile, ...] = MODEL_FILES

    def engine(self) -> Engine:
        if self.fake is not None:
            return FakeEngine(**self.fake)
        return AudioSeparatorEngine(self.models_dir, self.model_files)


def exit_with_parent() -> None:
    """A server killed outright (Task Manager, kill -9) can't stop its child, so the child
    watches it; otherwise the model would stay in GPU memory and a restart would load another."""
    parent = mp.parent_process()
    if parent is not None:
        parent.join()
        os._exit(0)


def worker_main(config: WorkerConfig, inbox: Any, outbox: Any, cancel: Event) -> None:
    threading.Thread(target=exit_with_parent, daemon=True).start()
    engine = config.engine()
    prepared: tuple[Preset, DevicePreference] | None = None
    while True:
        message = inbox.get()
        if message is None:
            return
        job_id, mixture, voice, scratch, preset, device = message

        def progress(done: int, total: int, job_id: str = job_id) -> None:
            outbox.put(("progress", job_id, done, total))

        try:
            if prepared != (preset, device):
                engine.prepare(preset, device)
                prepared = (preset, device)
            report = separate_chunked(
                engine,
                Path(mixture),
                Path(voice),
                Path(scratch),
                cancel.is_set,
                progress,
            )
            outbox.put(("done", job_id, report.chunks, report.cpu_fallbacks))
        except Canceled:
            outbox.put(("canceled", job_id))
        except ModelChecksumError as exc:
            prepared = None
            outbox.put(("error", job_id, str(exc)))
        except OSError as exc:
            message = DISK_FULL if exc.errno == errno.ENOSPC else f"The separation failed: {exc}"
            outbox.put(("error", job_id, message))
        except Exception as exc:
            outbox.put(("error", job_id, f"The separation failed: {exc}"))


class Worker:
    """The server's handle on the one child process that runs separations.

    `separate` fits the pipeline's separator once preset and device are bound. The child starts
    on first use and again after it dies.
    """

    def __init__(self, config: WorkerConfig, stall_s: float = STALL_S) -> None:
        self.config = config
        self.stall_s = stall_s
        self.ctx = mp.get_context("spawn")
        self.process: SpawnProcess | None = None
        self.lock = threading.Lock()

    def _start(self) -> None:
        self.inbox: Any = self.ctx.Queue()
        self.outbox: Any = self.ctx.Queue()
        self.cancel = self.ctx.Event()
        self.process = self.ctx.Process(
            target=worker_main,
            args=(self.config, self.inbox, self.outbox, self.cancel),
            daemon=True,
            name="sukoon-worker",
        )
        self.process.start()

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.is_alive():
            self.inbox.put(None)
            self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5)
        self.process = None

    def kill(self) -> None:
        if self.process is not None:
            self.process.kill()
            self.process.join(timeout=5)
            self.process = None

    def separate(
        self,
        mixture: Path,
        voice: Path,
        scratch: Path,
        cancelled: Callable[[], bool],
        on_chunk: Callable[[int, int], None],
        *,
        preset: Preset,
        device: DevicePreference,
    ) -> ChunkReport:
        with self.lock:
            if self.process is None or not self.process.is_alive():
                self._start()
            process = self.process
            if process is None:
                raise JobError(CRASHED)
            self.cancel.clear()
            job_id = scratch.name
            self.inbox.put((job_id, str(mixture), str(voice), str(scratch), preset, device))
            cancel_sent: float | None = None
            heard = time.monotonic()
            while True:
                if cancel_sent is None and cancelled():
                    self.cancel.set()
                    cancel_sent = time.monotonic()
                if cancel_sent is not None and time.monotonic() - cancel_sent > CANCEL_GRACE_S:
                    # The chunk did not come back in time; a fresh process is cheaper than waiting.
                    self.kill()
                    raise Canceled
                try:
                    message = self.outbox.get(timeout=0.2)
                except queue.Empty:
                    if not process.is_alive():
                        self.process = None
                        raise JobError(CRASHED) from None
                    if time.monotonic() - heard > self.stall_s:
                        self.kill()
                        raise JobError(STALLED) from None
                    continue
                heard = time.monotonic()
                kind, msg_job = message[0], message[1]
                if msg_job != job_id:
                    continue
                if kind == "progress":
                    on_chunk(message[2], message[3])
                elif kind == "done":
                    return ChunkReport(message[2], message[3])
                elif kind == "canceled":
                    raise Canceled
                else:
                    raise JobError(message[2])
