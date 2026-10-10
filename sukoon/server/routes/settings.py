"""The saved choices: model, device, and default output formats."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from sukoon.media import compat
from sukoon.media.encode import AUDIO_FORMATS
from sukoon.separation.models import PRESETS
from sukoon.server.services import Services


class SettingsBody(BaseModel):
    # Theme stays in the browser, so it is refused here rather than quietly dropped.
    model_config = ConfigDict(extra="forbid")

    preset: str | None = None
    device: str | None = None
    audio_format: str | None = None
    video_format: str | None = None


CHECKS = {
    "preset": lambda v: v in PRESETS,
    "device": lambda v: v in ("auto", "cpu"),
    "audio_format": lambda v: v is None or v in AUDIO_FORMATS,
    "video_format": lambda v: v is None or v in compat.VIDEO_CONTAINERS,
}


def router(services: Services) -> APIRouter:
    r = APIRouter()
    store = services.store

    def settings_view() -> dict[str, Any]:
        audio, video = list(AUDIO_FORMATS), list(compat.VIDEO_CONTAINERS)
        return {
            **store.settings(),
            "formats": {"audio": audio, "video": video},
            "missing": {f: e for f in [*audio, *video] if (e := services.missing_encoder(f))},
            "folder": str(services.settings.home),
        }

    @r.get("/settings")
    def get_settings() -> dict[str, Any]:
        return settings_view()

    @r.put("/settings")
    def put_settings(body: SettingsBody) -> dict[str, Any]:
        values = body.model_dump(exclude_unset=True)
        for key, value in values.items():
            if not CHECKS[key](value):
                raise HTTPException(400, f"{value!r} isn't a choice for {key}.")
        store.save_settings(values)
        return settings_view()

    return r
