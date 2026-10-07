"""A finished job's files: the result to download, and what the review player plays."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from sukoon.jobs.runner import source_path
from sukoon.media.naming import content_disposition
from sukoon.server.services import Services

VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}


def router(services: Services) -> APIRouter:
    r = APIRouter()
    settings = services.settings

    def finished_file(job_id: str, name: str, media_type: str) -> FileResponse:
        job = services.job_or_404(job_id)
        if job["state"] != "done":
            raise HTTPException(404, "This job has not finished.")
        path = settings.job_path("outputs", job_id) / name
        if not path.is_file():
            raise HTTPException(404, "There is no preview for this job.")
        return FileResponse(path, media_type=media_type)

    @r.get("/jobs/{job_id}/output")
    def output(job_id: str) -> FileResponse:
        job = services.job_or_404(job_id)
        if job["state"] != "done" or not job["result"]:
            raise HTTPException(404, "This job has no output yet.")
        path = settings.job_path("outputs", job_id) / job["result"]["output"]
        if not path.is_file():
            raise HTTPException(404, "The output file is missing.")
        name = services.view(job)["output_name"]
        return FileResponse(path, headers={"content-disposition": content_disposition(name)})

    @r.get("/jobs/{job_id}/peaks")
    def peaks(job_id: str) -> FileResponse:
        return finished_file(job_id, "peaks.json", "application/json")

    @r.get("/jobs/{job_id}/preview/{which}")
    def preview(job_id: str, which: str) -> FileResponse:
        if which not in ("original", "clean"):
            raise HTTPException(404, "No such preview.")
        return finished_file(job_id, f"preview-{which}.webm", "audio/webm")

    @r.get("/jobs/{job_id}/source")
    def source(job_id: str) -> FileResponse:
        """The uploaded video, for the review player; served in ranges so it can seek."""
        job = services.job_or_404(job_id)
        path = source_path(settings, job_id)
        if job["state"] != "done" or job["kind"] != "video" or path is None:
            raise HTTPException(404, "There is no video to preview.")
        return FileResponse(path, media_type=VIDEO_TYPES.get(path.suffix, "video/mp4"))

    return r
