"""Receiving a dropped file, and the checks every new file passes before it is queued, whether it
was uploaded or fetched from a link."""

import contextlib
import errno
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
from fastapi import HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

from sukoon.errors import JobError
from sukoon.jobs.pipeline import Options, output_format
from sukoon.jobs.store import Job
from sukoon.links.messages import SILENT
from sukoon.links.sites import NAMES, SITES
from sukoon.media.probe import MEDIA_EXTS, NO_SOUND, Rejected, probe
from sukoon.server.services import NO_SPACE, TOO_BIG, Services, disk_need, free_bytes
from sukoon.server.views import next_state
from sukoon.settings import GB


class _TooBig(Exception):
    pass


async def receive_upload(
    services: Services, request: Request, boundary: bytes, options: Options
) -> Job | None:
    """Streams the first file part to a .part file, then probes it and queues the job."""
    settings, store = services.settings, services.store
    state: dict[str, Any] = {
        "headers": {},
        "field": b"",
        "value": b"",
        "job": None,
        "size": 0,
        "done": False,
    }
    pending: list[bytes] = []

    def on_header_field(data: bytes, start: int, end: int) -> None:
        state["field"] += data[start:end]

    def on_header_value(data: bytes, start: int, end: int) -> None:
        state["value"] += data[start:end]

    def on_header_end() -> None:
        state["headers"][state["field"].lower()] = state["value"]
        state["field"], state["value"] = b"", b""

    def on_headers_finished() -> None:
        _, disp = parse_options_header(state["headers"].get(b"content-disposition", b""))
        if b"filename" in disp and state["job"] is None and not state["done"]:
            state["name"] = disp[b"filename"].decode("utf-8", "replace") or "untitled"

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if "name" in state and not state["done"]:
            pending.append(data[start:end])

    def on_part_end() -> None:
        if "name" in state:
            state["done"] = True
        state["headers"] = {}

    parser = MultipartParser(
        boundary,
        {
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
        },
    )

    job: Job | None = None
    folder: Path | None = None
    handle = None
    try:
        async for chunk in request.stream():
            parser.write(chunk)
            if "name" in state and job is None:
                job = store.create(state["name"], options.to_json())
                folder = settings.job_path("uploads", job["id"])
                folder.mkdir(parents=True, exist_ok=True)
                handle = await anyio.to_thread.run_sync((folder / "upload.part").open, "wb")
            if handle is not None and pending:
                data = b"".join(pending)
                pending.clear()
                state["size"] += len(data)
                if state["size"] > settings.max_upload_bytes:
                    raise _TooBig
                await anyio.to_thread.run_sync(handle.write, data)
        parser.finalize()
    except BaseException as exc:
        # Whatever stopped the upload, nothing it started may outlive it.
        if handle is not None:
            handle.close()
        if job is not None:
            with contextlib.suppress(KeyError):  # Already deleted from another tab.
                store.delete(job["id"])
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, _TooBig):
            raise HTTPException(
                413, TOO_BIG.format(limit=settings.max_upload_bytes // GB)
            ) from None
        if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            raise HTTPException(507, NO_SPACE) from None
        if isinstance(exc, MultipartParseError):
            raise HTTPException(400, "The upload was malformed.") from None
        raise
    if job is None or folder is None or handle is None:
        return None
    handle.close()
    suffix = Path(job["name"]).suffix.lower()
    source = folder / f"source{suffix if suffix in MEDIA_EXTS else ''}"
    (folder / "upload.part").replace(source)
    return await anyio.to_thread.run_sync(check_upload, services, job["id"], source, state["size"])


def check_upload(services: Services, job_id: str, source: Path, size: int) -> Job:
    """Probes a finished upload; rejected files are deleted and their job says why."""
    settings, store = services.settings, services.store
    if store.get(job_id)["state"] != "checking":
        # Cancelled while it was still uploading.
        shutil.rmtree(source.parent, ignore_errors=True)
        return store.get(job_id)
    try:
        result = probe(source, settings.max_duration_s)
    except Rejected as exc:
        shutil.rmtree(source.parent, ignore_errors=True)
        message, link = exc.message, store.get(job_id)["link"]
        if link and message == NO_SOUND:
            message = SILENT.format(name=NAMES[SITES[link["site"]]])
        return store.transition(job_id, "failed", error=message, retryable=False)
    if free_bytes(settings) < disk_need(result.duration, size):
        shutil.rmtree(source.parent, ignore_errors=True)
        return store.transition(job_id, "failed", error=NO_SPACE, retryable=False)
    job = store.get(job_id)
    options = Options(**job["options"])
    if options.format is None:
        saved = store.settings()
        preferred = saved["video_format"] if result.kind == "video" else saved["audio_format"]
        if job["link"]:
            # A link becomes a file that plays everywhere unless something else was chosen.
            preferred = "mp4" if result.kind == "video" else "m4a"
        if preferred and not services.missing_encoder(preferred):
            options = replace(options, format=preferred)
    try:
        fmt = output_format(result, options, store.get(job_id)["name"])
    except JobError as exc:
        shutil.rmtree(source.parent, ignore_errors=True)
        return store.transition(job_id, "failed", error=str(exc), retryable=False)
    options = replace(options, format=fmt)
    with services.runner.lock:
        if store.get(job_id)["state"] != "checking":
            # Cancelled while it was being probed.
            shutil.rmtree(source.parent, ignore_errors=True)
            return store.get(job_id)
        store.update(job_id, probe=result.to_json(), kind=result.kind, options=options.to_json())
        target = "awaiting_track" if len(result.audio) > 1 else next_state(result, options)
        job = store.transition(job_id, target)
    services.runner.notify()
    return job
