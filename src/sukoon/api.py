import asyncio
import contextlib
import json
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import ClientDisconnect

from sukoon import models
from sukoon.download import Downloads
from sukoon.encode import AUDIO_FORMATS
from sukoon.naming import content_disposition, download_name
from sukoon.pipeline import Options
from sukoon.probe import Rejected, probe
from sukoon.runner import Runner
from sukoon.settings import GB, Settings
from sukoon.store import Job, Store, TransitionError

KEEPALIVE_S = 15.0
# Kept on disk only for these, so ffmpeg never sees a playlist extension it might act on.
MEDIA_EXTS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".webm",
    ".mp4",
    ".m4v",
    ".mov",
    ".mkv",
    ".mka",
    ".avi",
    ".wma",
    ".wmv",
    ".aif",
    ".aiff",
    ".ts",
    ".mpg",
    ".mpeg",
}
SCRATCH_PER_HOUR = 2.6 * GB
HEADROOM = 1 * GB

TOO_BIG = "This file is bigger than {limit} GB, which is sukoon's limit."
QUEUE_FULL = "The queue is full ({limit} files). Add more once some have finished."
NO_SPACE = "There isn't enough free disk space for this file."


@dataclass
class Services:
    settings: Settings
    store: Store
    runner: Runner
    downloads: Downloads
    model_listeners: list[Callable[[dict[str, object]], None]] = field(default_factory=list)

    def model_changed(self, state: dict[str, object]) -> None:
        for listener in list(self.model_listeners):
            listener(state)


def public(job: Job) -> dict[str, Any]:
    """What the interface sees of a job."""
    p = job.get("probe") or {}
    result = job.get("result") or {}
    tracks = [
        {"language": s.get("language"), "title": s.get("title"), "channels": s.get("channels")}
        for s in p.get("streams", [])
        if s.get("codec_type") == "audio"
    ]
    fmt = result.get("format")
    return {
        "id": job["id"],
        "created": job["created"],
        "name": job["name"],
        "kind": job["kind"],
        "state": job["state"],
        "progress": job["progress"],
        "eta": job["eta"],
        "error": job["error"],
        "retryable": job["retryable"],
        "options": job["options"],
        "duration": p.get("duration"),
        "tracks": tracks,
        "notes": result.get("notes", []),
        "output_name": download_name(job["name"], AUDIO_FORMATS[fmt].ext) if fmt else None,
    }


def disk_need(duration_s: float, upload_bytes: int) -> float:
    """Scratch for the decoded audio, an output about the upload's size, and headroom."""
    return duration_s / 3600 * SCRATCH_PER_HOUR + upload_bytes + HEADROOM


def free_bytes(settings: Settings) -> int:
    return shutil.disk_usage(settings.home).free


def build_router(services: Services) -> APIRouter:
    router = APIRouter(prefix="/api")
    settings, store, runner = services.settings, services.store, services.runner

    def job_or_404(job_id: str) -> Job:
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "No such job.") from None

    def refuse(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    @router.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [public(j) for j in store.list()]

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return public(job_or_404(job_id))

    @router.post("/jobs", status_code=201, response_model=None)
    async def upload(request: Request) -> dict[str, Any] | JSONResponse:
        length = int(request.headers.get("content-length") or 0)
        if length > settings.max_upload_bytes + 64 * 1024:
            return refuse(413, TOO_BIG.format(limit=settings.max_upload_bytes // GB))
        waiting = store.count(
            "checking", "queued", "waiting_model", "awaiting_track", "awaiting_confirm"
        )
        if waiting >= settings.max_queued:
            return refuse(429, QUEUE_FULL.format(limit=settings.max_queued))
        if free_bytes(settings) < length + HEADROOM:
            return refuse(507, NO_SPACE)
        ctype, params = parse_options_header(request.headers.get("content-type", ""))
        if ctype != b"multipart/form-data" or b"boundary" not in params:
            return refuse(400, "Send the file as multipart form data.")
        preset = request.query_params.get("preset", "best")
        fmt = request.query_params.get("format") or None
        if preset not in models.PRESETS or (fmt is not None and fmt not in AUDIO_FORMATS):
            return refuse(400, "Unknown preset or format.")
        options = Options(preset=preset, format=fmt)
        try:
            job = await receive_upload(services, request, params[b"boundary"], options)
        except ClientDisconnect:
            return refuse(400, "The upload was interrupted.")
        if job is None:
            return refuse(400, "No file was sent.")
        return public(job)

    @router.get("/jobs/{job_id}/output")
    def output(job_id: str) -> FileResponse:
        job = job_or_404(job_id)
        if job["state"] != "done" or not job["result"]:
            raise HTTPException(404, "This job has no output yet.")
        path = settings.job_path("outputs", job_id) / job["result"]["output"]
        if not path.is_file():
            raise HTTPException(404, "The output file is missing.")
        name = public(job)["output_name"]
        return FileResponse(path, headers={"content-disposition": content_disposition(name)})

    @router.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        job_or_404(job_id)
        # A finished job ignores cancel, so a second click is harmless.
        with contextlib.suppress(TransitionError):
            runner.cancel(job_id)
        return public(store.get(job_id))

    @router.get("/models")
    def list_models() -> list[dict[str, object]]:
        return [services.downloads.state(p) for p in models.PRESETS]

    @router.post("/models/{preset}/download")
    def download(preset: str, switch: bool = False) -> dict[str, object]:
        """Starts a download; with switch, jobs waiting for another model move to this one."""
        if preset not in models.PRESETS:
            raise HTTPException(404, "No such preset.")
        if switch:
            for job in store.list():
                if job["state"] == "waiting_model":
                    store.update(job["id"], options={**job["options"], "preset": preset})
        services.downloads.start(preset)
        return services.downloads.state(preset)

    @router.get("/events")
    async def events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            event_stream(services),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache"},
        )

    return router


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
        "file": None,
        "size": 0,
        "done": False,
        "buffer": bytearray(),
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
    except (ClientDisconnect, _TooBig, OSError) as exc:
        if handle is not None:
            handle.close()
        if job is not None:
            store.delete(job["id"])
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, _TooBig):
            raise HTTPException(
                413, TOO_BIG.format(limit=settings.max_upload_bytes // GB)
            ) from None
        if isinstance(exc, OSError):
            raise HTTPException(507, NO_SPACE) from None
        raise
    if job is None or folder is None or handle is None:
        return None
    handle.close()
    suffix = Path(job["name"]).suffix.lower()
    source = folder / f"source{suffix if suffix in MEDIA_EXTS else ''}"
    (folder / "upload.part").replace(source)
    return await anyio.to_thread.run_sync(check_upload, services, job["id"], source, state["size"])


class _TooBig(Exception):
    pass


def check_upload(services: Services, job_id: str, source: Path, size: int) -> Job:
    """Probes a finished upload; rejected files are deleted and their job says why."""
    settings, store = services.settings, services.store
    try:
        result = probe(source, settings.max_duration_s)
    except Rejected as exc:
        shutil.rmtree(source.parent, ignore_errors=True)
        return store.transition(job_id, "failed", error=exc.message, retryable=False)
    if free_bytes(settings) < disk_need(result.duration, size):
        shutil.rmtree(source.parent, ignore_errors=True)
        return store.transition(job_id, "failed", error=NO_SPACE, retryable=False)
    store.update(job_id, probe=result.to_json(), kind=result.kind)
    if len(result.audio) > 1:
        return store.transition(job_id, "awaiting_track")
    job = store.transition(job_id, "queued")
    services.runner.notify()
    return job


def sse(event: str, data: object) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


async def event_stream(services: Services) -> AsyncIterator[bytes]:
    """A snapshot of every job on connect, then each change as it happens."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_job(event: str, job: Job) -> None:
        payload = sse("job", public(job)) if event == "job" else sse("deleted", {"id": job["id"]})
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    def on_model(state: dict[str, object]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, sse("model", state))

    unsubscribe = services.store.subscribe(on_job)
    services.model_listeners.append(on_model)
    try:
        yield sse(
            "snapshot",
            {
                "jobs": [public(j) for j in services.store.list()],
                "models": [services.downloads.state(p) for p in models.PRESETS],
            },
        )
        while True:
            try:
                yield await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except TimeoutError:
                yield b": keep-alive\n\n"
    finally:
        unsubscribe()
        services.model_listeners.remove(on_model)
