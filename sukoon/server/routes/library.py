"""The data folder: how much it holds, clearing finished jobs, and opening the outputs folder."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from sukoon.server.services import Services
from sukoon.settings import Settings


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


def router(services: Services) -> APIRouter:
    r = APIRouter()
    settings = services.settings

    @r.get("/library")
    def library() -> dict[str, Any]:
        return library_size(settings)

    @r.post("/library/clear")
    def clear() -> dict[str, Any]:
        removed = services.runner.clear_finished()
        return {"removed": removed, **library_size(settings)}

    @r.post("/library/open", status_code=204)
    def open_outputs() -> None:
        # Only ever the outputs folder; no path from the request reaches the file manager.
        open_folder(settings.area("outputs"))

    return r
