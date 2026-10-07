"""What every route shares: the store, the runner, the model downloads, and the checks a new job
must pass before it is accepted."""

import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from sukoon.jobs.runner import Runner
from sukoon.jobs.store import Job, Store
from sukoon.media import compat, tools
from sukoon.media.encode import AUDIO_FORMATS
from sukoon.separation.download import Downloads
from sukoon.server.views import public
from sukoon.settings import GB, Settings

SCRATCH_PER_HOUR = 2.6 * GB
HEADROOM = 1 * GB

TOO_BIG = "This file is bigger than {limit} GB, which is sukoon's limit."
QUEUE_FULL = "The queue is full ({limit} files). Add more once some have finished."
NO_SPACE = "There isn't enough free disk space for this file."
UNKNOWN = "Unknown preset or format."

# Jobs that count toward the queue limit.
WAITING = ("fetching", "checking", "queued", "waiting_model", "awaiting_track", "awaiting_confirm")


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

    def view(self, job: Job) -> dict[str, Any]:
        return public(job, self.missing_encoder)

    def job_or_404(self, job_id: str) -> Job:
        try:
            return self.store.get(job_id)
        except KeyError:
            raise HTTPException(404, "No such job.") from None

    def queue_full(self) -> bool:
        return self.store.count(*WAITING) >= self.settings.max_queued

    def format_refusal(self, fmt: str | None) -> str | None:
        """Why a requested output format can't be used, if it can't."""
        if fmt is None:
            return None
        if fmt not in AUDIO_FORMATS and fmt not in compat.VIDEO_CONTAINERS:
            return UNKNOWN
        if encoder := self.missing_encoder(fmt):
            return needs_encoder(fmt, encoder)
        return None


def needs_encoder(fmt: str, encoder: str) -> str:
    return f"{fmt.upper()} needs the {encoder} encoder, which this ffmpeg doesn't have."


def refuse(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def disk_need(duration_s: float, upload_bytes: int) -> float:
    """Scratch for the decoded audio, an output about the upload's size, and headroom."""
    return duration_s / 3600 * SCRATCH_PER_HOUR + upload_bytes + HEADROOM


def free_bytes(settings: Settings) -> int:
    return shutil.disk_usage(settings.home).free
