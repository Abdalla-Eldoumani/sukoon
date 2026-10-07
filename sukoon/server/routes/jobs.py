"""Adding, choosing, cancelling, retrying, and deleting jobs."""

import contextlib
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from python_multipart.multipart import parse_options_header
from starlette.requests import ClientDisconnect

from sukoon.errors import JobError
from sukoon.jobs.pipeline import Options, output_format
from sukoon.jobs.runner import RunnerError
from sukoon.jobs.store import TransitionError
from sukoon.media.probe import Probe
from sukoon.separation.models import PRESETS
from sukoon.server.fetches import start_fetch
from sukoon.server.services import (
    HEADROOM,
    NO_SPACE,
    QUEUE_FULL,
    TOO_BIG,
    UNKNOWN,
    Services,
    free_bytes,
    needs_encoder,
    refuse,
)
from sukoon.server.uploads import receive_upload
from sukoon.server.views import next_state
from sukoon.settings import GB

# States a job can still be changed in before it runs.
CHOOSABLE = {"awaiting_track", "awaiting_confirm", "queued", "waiting_model"}


class Choice(BaseModel):
    track: int | None = None
    format: str | None = None
    confirm: bool = False
    keep_music: bool | None = None


def router(services: Services) -> APIRouter:
    r = APIRouter()
    settings, store, runner = services.settings, services.store, services.runner

    @r.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [services.view(j) for j in store.list()]

    @r.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return services.view(services.job_or_404(job_id))

    @r.post("/jobs", status_code=201, response_model=None)
    async def upload(request: Request) -> dict[str, Any] | JSONResponse:
        length = int(request.headers.get("content-length") or 0)
        if length > settings.max_upload_bytes + 64 * 1024:
            return refuse(413, TOO_BIG.format(limit=settings.max_upload_bytes // GB))
        if services.queue_full():
            return refuse(429, QUEUE_FULL.format(limit=settings.max_queued))
        if free_bytes(settings) < length + HEADROOM:
            return refuse(507, NO_SPACE)
        ctype, params = parse_options_header(request.headers.get("content-type", ""))
        if ctype != b"multipart/form-data" or b"boundary" not in params:
            return refuse(400, "Send the file as multipart form data.")
        saved = store.settings()
        preset = request.query_params.get("preset") or saved["preset"]
        fmt = request.query_params.get("format") or None
        if preset not in PRESETS:
            return refuse(400, UNKNOWN)
        if reason := services.format_refusal(fmt):
            return refuse(400, reason)
        options = Options(preset=preset, device=saved["device"], format=fmt)
        try:
            job = await receive_upload(services, request, params[b"boundary"], options)
        except ClientDisconnect:
            return refuse(400, "The upload was interrupted.")
        if job is None:
            return refuse(400, "No file was sent.")
        return services.view(job)

    @r.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        services.job_or_404(job_id)
        # A finished job ignores cancel, so a second click is harmless.
        with contextlib.suppress(TransitionError):
            runner.cancel(job_id)
        return services.view(store.get(job_id))

    @r.post("/jobs/{job_id}/choose")
    def choose(job_id: str, body: Choice) -> dict[str, Any]:
        """Picks the audio track and output format, and confirms a re-encode, before a job runs."""
        with runner.lock:
            job = services.job_or_404(job_id)
            old = Options(**job["options"])
            kept = old.keep_music if body.keep_music is None else body.keep_music
            if job["state"] in ("fetching", "checking"):
                # Nothing is known about the file yet; the format is checked once it is.
                early = replace(old, keep_music=kept, format=body.format or old.format)
                return services.view(store.update(job_id, options=early.to_json()))
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
        return services.view(job)

    @r.post("/jobs/{job_id}/retry")
    def retry(job_id: str) -> dict[str, Any]:
        job = services.job_or_404(job_id)
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
            return services.view(store.get(job_id))
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
        return services.view(store.get(job_id))

    @r.delete("/jobs/{job_id}", status_code=204)
    def delete(job_id: str) -> None:
        services.job_or_404(job_id)
        try:
            runner.delete(job_id)
        except RunnerError as exc:
            raise HTTPException(409, str(exc)) from None

    return r
