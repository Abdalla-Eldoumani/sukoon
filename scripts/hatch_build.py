import runpy
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CopyWebHook(BuildHookInterface):  # type: ignore[type-arg]
    """Copies a built web interface into the wheel's package folder when one exists."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel" or version == "editable":
            return
        build_web = runpy.run_path(str(Path(self.root) / "scripts" / "build_web.py"))
        if (build_web["DIST"] / "index.html").is_file():
            build_web["copy_dist"]()
