import asyncio
import contextlib
import errno
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import ClientDisconnect

from sukoon import compat, links, models, tools
from sukoon.download import Downloads
from sukoon.encode import AUDIO_FORMATS
from sukoon.errors import Canceled, JobError
from sukoon.naming import SUFFIX, content_disposition, download_name
from sukoon.pipeline import Options, extension, output_format
from sukoon.probe import MEDIA_EXTS, NO_SOUND, Probe, Rejected, probe
from sukoon.runner import Runner, RunnerError, source_path
from sukoon.settings import GB, Settings
from sukoon.store import Job, Store, TransitionError

log = logging.getLogger("sukoon")

KEEPALIVE_S = 15.0
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}
SCRATCH_PER_HOUR = 2.6 * GB
HEADROOM = 1 * GB

TOO_BIG = "This file is bigger than {limit} GB, which is sukoon's limit."
QUEUE_FULL = "The queue is full ({limit} files). Add more once some have finished."
NO_SPACE = "There isn't enough free disk space for this file."


CHOOSABLE = {"awaiting_track", "awaiting_confirm", "queued", "waiting_model"}
WAITING = ("fetching", "checking", "queued", "waiting_model", "awaiting_track", "awaiting_confirm")


class SettingsBody(BaseModel):
    # Theme stays in the browser, so it is refused here rather than quietly dropped.
    model_config = ConfigDict(extra="forbid")

    preset: str | None = None
    device: str | None = None
    audio_format: str | None = None
    video_format: str | None = None


def needs_encoder(fmt: str, encoder: str) -> str:
    return f"{fmt.upper()} needs the {encoder} encoder, which this ffmpeg doesn't have."


class Choice(BaseModel):
    track: int | None = None
    format: str | None = None
    confirm: bool = False
    keep_music: bool | None = None


class LinkBody(BaseModel):
    url: str
    keep_music: bool = False
    format: str | None = None


@dataclass
class Services:
    settings: Settings
    store: Store
    runner: Runner
    downloads: Downloads
    encoders: set[str] | None = None
    model_listeners: list[Callable[[dict[str, object]], None]] = field(default_factory=list)
    # Tests put a stand-in downloader here.
    fetch_options: dict[str, Any] = field(default_factory=dict)
    fetches: dict[str, threading.Thread] = field(default_factory=dict)

    def available_encoders(self) -> set[str]:
        # Listed once; again only if ffmpeg was missing at startup and has appeared since.
        if self.encoders is None and tools.ffmpeg_path():
            self.encoders = tools.available_encoders()
        return self.encoders or set()

    def missing_encoder(self, fmt: str) -> str | None:
        """The ffmpeg encoder a format needs and this ffmpeg lacks, if any."""
        encoder = (
            AUDIO_FORMATS[fmt].encoder
            if fmt in AUDIO_FORMATS
            else (compat.AUDIO_ENCODER[fmt][0] if fmt in compat.AUDIO_ENCODER else None)
        )
        return encoder if encoder and encoder not in self.available_encoders() else None

    def model_changed(self, state: dict[str, object]) -> None:
        for listener in list(self.model_listeners):
            listener(state)


def format_choices(
    probe: Probe, track: int, missing: Callable[[str], str | None] = lambda f: None
) -> list[dict[str, Any]]:
    """Every output format this job can have, marking the ones that re-encode the picture
    and the ones this ffmpeg cannot write."""
    audio = [
        {"value": f, "video": False, "reencode": False, "missing": missing(f)}
        for f in AUDIO_FORMATS
    ]
    if probe.kind != "video":
        return audio
    video = [
        {
            "value": c,
            "video": True,
            "reencode": compat.plan(probe, track, c).reencode is not None,
            "missing": missing(c),
        }
        for c in compat.VIDEO_CONTAINERS
    ]
    return video + audio


def next_state(probe: Probe, options: Options) -> str:
    """Queued, or held for a confirm when the chosen container makes the picture re-encode."""
    if options.format in compat.VIDEO_CONTAINERS:
        track = options.track if options.track is not None else probe.default_audio()
        if compat.plan(probe, track, options.format).reencode and not options.reencode_ok:
            return "awaiting_confirm"
    return "queued"


def public(job: Job, missing: Callable[[str], str | None] = lambda f: None) -> dict[str, Any]:
    """What the interface sees of a job."""
    p = job.get("probe") or {}
    result = job.get("result") or {}
    choices: list[dict[str, Any]] = []
    confirm = None
    offset = 0.0
    if p:
        probe_ = Probe.from_json(p)
        options = Options(**job["options"])
        track = options.track if options.track is not None else probe_.default_audio()
        choices = format_choices(probe_, track, missing)
        if probe_.video:
            # Where the previews' time zero sits on the video's timeline.
            offset = probe_.audio[track].start_time - probe_.video[0].start_time
        if job["state"] == "awaiting_confirm" and options.format in compat.VIDEO_CONTAINERS:
            confirm = compat.plan(probe_, track, options.format).confirm_message
    tracks = [
        {
            "language": s.get("language"),
            "title": s.get("title"),
            "channels": s.get("channels"),
            "default": s.get("default", False),
        }
        for s in p.get("streams", [])
        if s.get("codec_type") == "audio"
    ]
    fmt = result.get("format")
    suffix = "" if job["options"].get("keep_music") else SUFFIX
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
        "formats": choices,
        "offset": round(offset, 6),
        "confirm": confirm,
        "output_name": download_name(job["name"], extension(fmt), suffix) if fmt else None,
        "link": job.get("link"),
    }


def folder_size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def library_size(settings: Settings) -> dict[str, Any]:
    """Bytes held by jobs (what Clear finished frees) and by models, and where they live."""
    jobs = sum(folder_size(settings.area(a)) for a in ("uploads", "work", "outputs"))
    return {
        "jobs": jobs,
        "models": folder_size(settings.area("models")),
        "folder": str(settings.home),
    }


def open_folder(folder: Path) -> None:
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


def disk_need(duration_s: float, upload_bytes: int) -> float:
    """Scratch for the decoded audio, an output about the upload's size, and headroom."""
    return duration_s / 3600 * SCRATCH_PER_HOUR + upload_bytes + HEADROOM


def free_bytes(settings: Settings) -> int:
    return shutil.disk_usage(settings.home).free


def build_router(services: Services) -> APIRouter:
    router = APIRouter(prefix="/api")
    settings, store, runner = services.settings, services.store, services.runner

    def view(job: Job) -> dict[str, Any]:
        return public(job, services.missing_encoder)

    def job_or_404(job_id: str) -> Job:
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "No such job.") from None

    def refuse(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    @router.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [view(j) for j in store.list()]

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return view(job_or_404(job_id))

    @router.post("/jobs", status_code=201, response_model=None)
    async def upload(request: Request) -> dict[str, Any] | JSONResponse:
        length = int(request.headers.get("content-length") or 0)
        if length > settings.max_upload_bytes + 64 * 1024:
            return refuse(413, TOO_BIG.format(limit=settings.max_upload_bytes // GB))
        if store.count(*WAITING) >= settings.max_queued:
            return refuse(429, QUEUE_FULL.format(limit=settings.max_queued))
        if free_bytes(settings) < length + HEADROOM:
            return refuse(507, NO_SPACE)
        ctype, params = parse_options_header(request.headers.get("content-type", ""))
        if ctype != b"multipart/form-data" or b"boundary" not in params:
            return refuse(400, "Send the file as multipart form data.")
        saved = store.settings()
        preset = request.query_params.get("preset") or saved["preset"]
        fmt = request.query_params.get("format") or None
        known = fmt is None or fmt in AUDIO_FORMATS or fmt in compat.VIDEO_CONTAINERS
        if preset not in models.PRESETS or not known:
            return refuse(400, "Unknown preset or format.")
        if fmt and (encoder := services.missing_encoder(fmt)):
            return refuse(400, needs_encoder(fmt, encoder))
        options = Options(preset=preset, device=saved["device"], format=fmt)
        try:
            job = await receive_upload(services, request, params[b"boundary"], options)
        except ClientDisconnect:
            return refuse(400, "The upload was interrupted.")
        if job is None:
            return refuse(400, "No file was sent.")
        return view(job)

    @router.post("/links", status_code=201, response_model=None)
    def add_link(body: LinkBody) -> dict[str, Any] | JSONResponse:
        """One link, one job: fetched first, then checked and run like a dropped file."""
        url = body.url.strip()
        try:
            name = links.site(url)
        except links.LinkRefused as exc:
            return refuse(400, exc.message)
        if store.count(*WAITING) >= settings.max_queued:
            return refuse(429, QUEUE_FULL.format(limit=settings.max_queued))
        fmt = body.format or None
        if fmt and fmt not in AUDIO_FORMATS and fmt not in compat.VIDEO_CONTAINERS:
            return refuse(400, "Unknown preset or format.")
        if fmt and (encoder := services.missing_encoder(fmt)):
            return refuse(400, needs_encoder(fmt, encoder))
        saved = store.settings()
        options = Options(
            preset=saved["preset"], device=saved["device"], format=fmt, keep_music=body.keep_music
        )
        job = store.create(
            url.split("://", 1)[1],
            options.to_json(),
            state="fetching",
            link={"url": url, "site": name, "done": 0, "total": None},
        )
        start_fetch(services, job["id"])
        return view(job)

    @router.get("/jobs/{job_id}/output")
    def output(job_id: str) -> FileResponse:
        job = job_or_404(job_id)
        if job["state"] != "done" or not job["result"]:
            raise HTTPException(404, "This job has no output yet.")
        path = settings.job_path("outputs", job_id) / job["result"]["output"]
        if not path.is_file():
            raise HTTPException(404, "The output file is missing.")
        name = view(job)["output_name"]
        return FileResponse(path, headers={"content-disposition": content_disposition(name)})

    def finished_file(job_id: str, name: str, media_type: str) -> FileResponse:
        job = job_or_404(job_id)
        if job["state"] != "done":
            raise HTTPException(404, "This job has not finished.")
        path = settings.job_path("outputs", job_id) / name
        if not path.is_file():
            raise HTTPException(404, "There is no preview for this job.")
        return FileResponse(path, media_type=media_type)

    @router.get("/jobs/{job_id}/peaks")
    def peaks(job_id: str) -> FileResponse:
        return finished_file(job_id, "peaks.json", "application/json")

    @router.get("/jobs/{job_id}/preview/{which}")
    def preview(job_id: str, which: str) -> FileResponse:
        if which not in ("original", "clean"):
            raise HTTPException(404, "No such preview.")
        return finished_file(job_id, f"preview-{which}.webm", "audio/webm")

    @router.get("/jobs/{job_id}/source")
    def source(job_id: str) -> FileResponse:
        """The uploaded video, for the review player; served in ranges so it can seek."""
        job = job_or_404(job_id)
        path = source_path(settings, job_id)
        if job["state"] != "done" or job["kind"] != "video" or path is None:
            raise HTTPException(404, "There is no video to preview.")
        return FileResponse(path, media_type=VIDEO_TYPES.get(path.suffix, "video/mp4"))

    @router.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        job_or_404(job_id)
        # A finished job ignores cancel, so a second click is harmless.
        with contextlib.suppress(TransitionError):
            runner.cancel(job_id)
        return view(store.get(job_id))

    @router.post("/jobs/{job_id}/choose")
    def choose(job_id: str, body: Choice) -> dict[str, Any]:
        """Picks the audio track and output format, and confirms a re-encode, before a job runs."""
        with runner.lock:
            job = job_or_404(job_id)
            old = Options(**job["options"])
            kept = old.keep_music if body.keep_music is None else body.keep_music
            if job["state"] in ("fetching", "checking"):
                # Nothing is known about the file yet; the format is checked once it is.
                early = replace(old, keep_music=kept, format=body.format or old.format)
                return view(store.update(job_id, options=early.to_json()))
            if job["state"] not in CHOOSABLE:
                raise HTTPException(409, "This job has already started.")
            p = Probe.from_json(job["probe"])
            track = old.track if body.track is None else body.track
            if track is not None and not 0 <= track < len(p.audio):
                raise HTTPException(400, "That audio track doesn't exist in this file.")
            fmt = body.format or old.format
            if body.format and (encoder := services.missing_encoder(body.format)):
                raise HTTPException(400, needs_encoder(body.format, encoder))
            try:
                fmt = output_format(p, replace(old, format=fmt), job["name"])
            except JobError as exc:
                raise HTTPException(400, str(exc)) from None
            options = replace(
                old,
                track=track,
                format=fmt,
                reencode_ok=body.confirm or (old.reencode_ok and fmt == old.format),
                keep_music=kept,
            )
            target = next_state(p, options)
            # A format change alone does not answer the track question.
            if job["state"] == "awaiting_track" and body.track is None:
                target = "awaiting_track"
            if target == job["state"]:
                job = store.update(job_id, options=options.to_json())
            else:
                job = store.transition(job_id, target, options=options.to_json())
        runner.notify()
        return view(job)

    @router.post("/jobs/{job_id}/retry")
    def retry(job_id: str) -> dict[str, Any]:
        job = job_or_404(job_id)
        if job["link"] and job["probe"] is None:
            # The fetch never finished, so it starts again, once the last one has let go of the
            # folder: it only notices a Cancel when it next looks, and its child takes a moment.
            last = services.fetches.get(job_id)
            if last is not None:
                last.join(timeout=10)
                if last.is_alive():
                    raise HTTPException(
                        409, "The last download is still stopping. Retry in a moment."
                    )
            try:
                runner.retry(job_id, "fetching")
            except RunnerError as exc:
                raise HTTPException(409, str(exc)) from None
            start_fetch(services, job_id)
            return view(store.get(job_id))
        target = "queued"
        if job["probe"]:
            p, options = Probe.from_json(job["probe"]), Options(**job["options"])
            target = next_state(p, options)
            if len(p.audio) > 1 and options.track is None:
                target = "awaiting_track"
        try:
            runner.retry(job_id, target)
        except RunnerError as exc:
            raise HTTPException(409, str(exc)) from None
        return view(store.get(job_id))

    @router.delete("/jobs/{job_id}", status_code=204)
    def delete(job_id: str) -> None:
        job_or_404(job_id)
        try:
            runner.delete(job_id)
        except RunnerError as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get("/settings")
    def get_settings() -> dict[str, Any]:
        return settings_view()

    @router.put("/settings")
    def put_settings(body: SettingsBody) -> dict[str, Any]:
        values = body.model_dump(exclude_unset=True)
        checks = {
            "preset": lambda v: v in models.PRESETS,
            "device": lambda v: v in ("auto", "cpu"),
            "audio_format": lambda v: v is None or v in AUDIO_FORMATS,
            "video_format": lambda v: v is None or v in compat.VIDEO_CONTAINERS,
        }
        for key, value in values.items():
            if not checks[key](value):
                raise HTTPException(400, f"{value!r} isn't a choice for {key}.")
        store.save_settings(values)
        return settings_view()

    def settings_view() -> dict[str, Any]:
        formats = [*AUDIO_FORMATS, *compat.VIDEO_CONTAINERS]
        return {
            **store.settings(),
            "missing": {f: e for f in formats if (e := services.missing_encoder(f))},
            "folder": str(settings.home),
        }

    @router.get("/library")
    def library() -> dict[str, Any]:
        return library_size(settings)

    @router.post("/library/clear")
    def clear() -> dict[str, Any]:
        removed = runner.clear_finished()
        return {"removed": removed, **library_size(settings)}

    @router.post("/library/open", status_code=204)
    def open_outputs() -> None:
        # Only ever the outputs folder; no path from the request reaches the file manager.
        open_folder(settings.area("outputs"))

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


class _TooBig(Exception):
    pass


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
            message = links.SILENT.format(name=links.NAMES[links.SITES[link["site"]]])
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
        fetched = links.fetch(
            job["link"]["url"],
            folder,
            progress,
            cancelled,
            settings.max_duration_s,
            settings.max_upload_bytes,
            **services.fetch_options,
        )
        source = links.assemble(folder, fetched.parts, cancelled)
    except Canceled:
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


def sse(event: str, data: object) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


async def event_stream(services: Services) -> AsyncIterator[bytes]:
    """A snapshot of every job on connect, then each change as it happens."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def view(job: Job) -> dict[str, Any]:
        return public(job, services.missing_encoder)

    def on_job(event: str, job: Job) -> None:
        payload = sse("job", view(job)) if event == "job" else sse("deleted", {"id": job["id"]})
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    def on_model(state: dict[str, object]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, sse("model", state))

    unsubscribe = services.store.subscribe(on_job)
    services.model_listeners.append(on_model)
    try:
        yield sse(
            "snapshot",
            {
                "jobs": [view(j) for j in services.store.list()],
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
