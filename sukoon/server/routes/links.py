"""Adding a job from a pasted link."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sukoon.jobs.pipeline import Options
from sukoon.links.sites import LinkRefused, site
from sukoon.server.fetches import start_fetch
from sukoon.server.services import QUEUE_FULL, Services, refuse


class LinkBody(BaseModel):
    url: str
    keep_music: bool = False
    format: str | None = None


def router(services: Services) -> APIRouter:
    r = APIRouter()
    settings, store = services.settings, services.store

    @r.post("/links", status_code=201, response_model=None)
    def add_link(body: LinkBody) -> dict[str, Any] | JSONResponse:
        """One link, one job: fetched first, then checked and run like a dropped file."""
        url = body.url.strip()
        try:
            name = site(url)
        except LinkRefused as exc:
            return refuse(400, exc.message)
        if services.queue_full():
            return refuse(429, QUEUE_FULL.format(limit=settings.max_queued))
        fmt = body.format or None
        if reason := services.format_refusal(fmt):
            return refuse(400, reason)
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
        return services.view(job)

    return r
