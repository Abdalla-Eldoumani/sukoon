import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Area = Literal["uploads", "work", "outputs", "models"]
AREAS: tuple[Area, ...] = ("uploads", "work", "outputs", "models")

GB = 1024**3


class UnsafePathError(ValueError):
    pass


def default_home() -> Path:
    env = os.environ.get("SUKOON_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "sukoon" if base else Path.home() / "AppData" / "Local" / "sukoon"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "sukoon"
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) / "sukoon" if xdg else Path.home() / ".local" / "share" / "sukoon"


@dataclass(frozen=True)
class Settings:
    home: Path = field(default_factory=default_home)
    max_upload_bytes: int = 8 * GB
    max_duration_s: float = 6 * 3600
    max_queued: int = 50
    port_first: int = 8417
    port_last: int = 8427

    def __post_init__(self) -> None:
        object.__setattr__(self, "home", self.home.expanduser().resolve())

    def ensure_dirs(self) -> None:
        for area in AREAS:
            (self.home / area).mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.home / "jobs.db"

    def area(self, area: Area) -> Path:
        return self.home / area

    def job_path(self, area: Area, job_id: str) -> Path:
        """The one way to build a per-job path; refuses anything outside the data folder."""
        try:
            canonical = str(uuid.UUID(job_id))
        except ValueError as exc:
            raise UnsafePathError(f"not a job id: {job_id!r}") from exc
        if canonical != job_id:
            raise UnsafePathError(f"not a job id: {job_id!r}")
        if area not in AREAS:
            raise UnsafePathError(f"unknown area: {area!r}")
        path = (self.home / area / job_id).resolve()
        if not path.is_relative_to(self.home / area):
            raise UnsafePathError(f"outside the data folder: {path}")
        return path
