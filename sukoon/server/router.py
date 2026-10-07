from fastapi import APIRouter

from sukoon.server.routes import events, files, jobs, library, links, models, settings
from sukoon.server.services import Services


def build_router(services: Services) -> APIRouter:
    """Every /api route, one module per area."""
    api = APIRouter(prefix="/api")
    for area in (jobs, links, files, settings, library, models, events):
        api.include_router(area.router(services))
    return api
