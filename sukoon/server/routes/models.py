"""The two separation models: whether each is downloaded, and starting a download."""

from fastapi import APIRouter, HTTPException

from sukoon.separation.models import PRESETS
from sukoon.server.services import Services


def router(services: Services) -> APIRouter:
    r = APIRouter()
    store, downloads = services.store, services.downloads

    @r.get("/models")
    def list_models() -> list[dict[str, object]]:
        return [downloads.state(p) for p in PRESETS]

    @r.post("/models/{preset}/download")
    def download(preset: str, switch: bool = False) -> dict[str, object]:
        """Starts a download; with switch, jobs waiting for another model move to this one."""
        if preset not in PRESETS:
            raise HTTPException(404, "No such preset.")
        if switch:
            for job in store.list():
                if job["state"] == "waiting_model":
                    store.update(job["id"], options={**job["options"], "preset": preset})
        downloads.start(preset)
        return downloads.state(preset)

    return r
