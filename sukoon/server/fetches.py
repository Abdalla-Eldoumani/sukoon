"""Running a link job's download on a thread, then handing the file to the upload checks."""

import contextlib
import logging
import shutil
import sqlite3
import threading
import time

from sukoon.errors import Canceled, JobError
from sukoon.jobs.store import TransitionError
from sukoon.links.fetch import assemble, fetch
from sukoon.server.services import Services
from sukoon.server.uploads import check_upload

log = logging.getLogger("sukoon")


def start_fetch(services: Services, job_id: str) -> None:
    thread = threading.Thread(
        target=run_fetch, args=(services, job_id), daemon=True, name="sukoon-fetch"
    )
    services.fetches[job_id] = thread
    thread.start()


def run_fetch(services: Services, job_id: str) -> None:
    """Fetches a link job's file, then hands it to the same checks an upload gets."""
    settings, store = services.settings, services.store
    job = store.get(job_id)
    folder = settings.job_path("uploads", job_id)
    shutil.rmtree(folder, ignore_errors=True)
    first: tuple[float, int] | None = None

    def progress(done: int, total: int | None) -> None:
        nonlocal first
        now = time.monotonic()
        first = first or (now, done)
        rate = (done - first[1]) / max(now - first[0], 1e-6)
        eta = (total - done) / rate if total and rate > 0 else None
        link = {**job["link"], "done": done, "total": total}
        store.update(job_id, progress=done / total if total else 0.0, eta=eta, link=link)

    def cancelled() -> bool:
        try:
            return bool(store.get(job_id)["state"] != "fetching")
        # Deleted, or the app is stopping; either way the download ends here.
        except (KeyError, sqlite3.ProgrammingError):
            return True

    try:
        fetched = fetch(
            job["link"]["url"],
            folder,
            progress,
            cancelled,
            settings.max_duration_s,
            settings.max_upload_bytes,
            **services.fetch_options,
        )
        source = assemble(folder, fetched.parts, cancelled)
    except Canceled:
        shutil.rmtree(folder, ignore_errors=True)
        return
    except sqlite3.ProgrammingError:
        # The store closed under a progress update: the app is stopping, and the next start
        # marks this job interrupted.
        shutil.rmtree(folder, ignore_errors=True)
        return
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        if not isinstance(exc, JobError):
            log.exception("fetching job %s failed", job_id)
        message = str(exc) if isinstance(exc, JobError) else f"Something went wrong: {exc}"
        with contextlib.suppress(KeyError, TransitionError, sqlite3.ProgrammingError):
            store.transition(job_id, "failed", error=message, eta=None)
        return
    with services.runner.lock:
        try:
            still = store.get(job_id)["state"] == "fetching"
        except KeyError:
            still = False
        if not still:
            shutil.rmtree(folder, ignore_errors=True)
            return
        name = f"{fetched.title}{source.suffix}"
        store.update(job_id, name=name, progress=0.0, eta=None)
        store.transition(job_id, "checking")
    check_upload(services, job_id, source, source.stat().st_size)
