import importlib.util
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CopyWebHook(BuildHookInterface):  # type: ignore[type-arg]
    """Copies a built web interface into the wheel's package folder when one exists."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel" or version == "editable":
            return
        path = Path(self.root) / "scripts" / "build_web.py"
        spec = importlib.util.spec_from_file_location("build_web", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if (module.DIST / "index.html").is_file():
            module.copy_dist()
