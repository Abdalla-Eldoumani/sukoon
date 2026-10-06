"""Builds the web interface and copies it into the package, where the server serves it from.

Usage: python scripts/build_web.py [--copy-only]
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DIST = WEB / "dist"
TARGET = ROOT / "src" / "sukoon" / "web_dist"


def npm(*args: str) -> None:
    exe = shutil.which("npm")
    if exe is None:
        raise SystemExit("npm was not found. Install Node.js 22.13 or newer.")
    subprocess.run([exe, "--prefix", str(WEB), *args], check=True)


def copy_dist() -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit(f"{DIST} has no index.html; build the web interface first.")
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(DIST, TARGET)


def main(argv: list[str]) -> int:
    if "--copy-only" not in argv:
        if not (WEB / "node_modules").is_dir():
            npm("ci")
        npm("run", "build")
    copy_dist()
    print(f"copied {DIST} to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
