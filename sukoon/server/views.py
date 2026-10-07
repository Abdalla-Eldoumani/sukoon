"""What the interface sees of a job, and the format choices it offers."""

from collections.abc import Callable
from typing import Any

from sukoon.jobs.pipeline import Options, extension, through
from sukoon.jobs.store import Job
from sukoon.media import compat
from sukoon.media.encode import AUDIO_FORMATS
from sukoon.media.naming import SUFFIX, download_name
from sukoon.media.probe import Probe


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
        "through": through(job["state"], job["progress"], bool(job["options"].get("keep_music"))),
    }
