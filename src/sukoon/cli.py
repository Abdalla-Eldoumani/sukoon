import argparse
import functools
import importlib.util
import io
import json
import shutil
import socket
import sys
import urllib.request
import uuid
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sukoon import doctor
from sukoon.compat import VIDEO_CONTAINERS
from sukoon.encode import AUDIO_FORMATS
from sukoon.settings import Settings

SEPARATION_MODULES = ("torch", "audio_separator")

if TYPE_CHECKING:
    from sukoon.engine import Engine
    from sukoon.models import Preset
    from sukoon.pipeline import Options


def is_sukoon(port: int) -> bool:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/health", headers={"host": f"127.0.0.1:{port}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=1) as r:  # noqa: S310 - fixed loopback URL
            return bool(json.load(r).get("app") == "sukoon")
    except (OSError, ValueError):
        return False


def bind_first_free(first: int, last: int) -> tuple[socket.socket | None, int]:
    """Returns a bound socket on the first free port, or (None, port) if sukoon already has one."""
    for port in range(first, last + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Lets a restart reclaim its port from TIME_WAIT; Windows needs the exclusive flag
        # instead, since its SO_REUSEADDR would let two servers share the port.
        if sys.platform == "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.close()
            if is_sukoon(port):
                return None, port
            continue
        return sock, port
    raise SystemExit(f"Ports {first} to {last} are all in use. Close something and try again.")


def serve(settings: Settings, open_browser: bool) -> int:
    import uvicorn

    from sukoon.app import create_app
    from sukoon.device import detect_cached

    sock, port = bind_first_free(settings.port_first, settings.port_last)
    url = f"http://127.0.0.1:{port}/"
    if sock is None:
        print(f"sukoon is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return 0
    settings.ensure_dirs()
    # Importing torch takes seconds; doing it now keeps the first health check fast.
    detect_cached()
    print(f"sukoon is running at {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    config = uvicorn.Config(create_app(settings, port), log_level="warning")
    uvicorn.Server(config).run(sockets=[sock])
    return 0


def free_name(folder: Path, name: str) -> Path:
    path = folder / name
    stem, dot, ext = name.rpartition(".")
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}){dot}{ext}"
        n += 1
    return path


def clean(
    files: Sequence[Path | str],
    out_dir: Path | None,
    options: "Options",
    engine: "Engine",
    settings: Settings,
    out: Callable[[str], None] = print,
    fetch_options: dict[str, Any] | None = None,
) -> int:
    """The browser's pipeline, run from the terminal one file or link at a time.

    Returns 1 if anything failed. A link is fetched first and its result lands in `out_dir`,
    or the current folder.
    """
    from dataclasses import replace

    from sukoon import links, pipeline
    from sukoon.chunk import separate_chunked
    from sukoon.models import ModelChecksumError, ModelMissingError
    from sukoon.naming import SUFFIX, download_name
    from sukoon.probe import probe

    settings.ensure_dirs()
    if not options.keep_music:
        try:
            engine.prepare(options.preset, options.device)
        except (ModelChecksumError, ModelMissingError, ImportError) as exc:
            out(str(exc))
            return 1
    failed = 0
    for item in files:
        job = str(uuid.uuid4())
        work, staging = settings.job_path("work", job), settings.job_path("outputs", job)
        fetched = settings.job_path("uploads", job)
        label = item if isinstance(item, str) else item.name

        def progress(stage: str, fraction: float, eta: float | None, name: str = label) -> None:
            left = f"  {int(eta) // 60}:{int(eta) % 60:02d} left" if eta is not None else ""
            sys.stderr.write(f"\r{name}  {stage.capitalize():<10} {fraction * 100:5.1f}%{left}   ")
            sys.stderr.flush()

        def fetching(done: int, total: int | None, name: str = label) -> None:
            of = f" of {total / 1e6:.0f}" if total else ""
            sys.stderr.write(f"\r{name}  Fetching   {done / 1e6:.1f}{of} MB   ")
            sys.stderr.flush()

        try:
            chosen = options
            if isinstance(item, str):
                links.site(item)
                got = links.fetch(
                    item,
                    fetched,
                    fetching,
                    lambda: False,
                    settings.max_duration_s,
                    settings.max_upload_bytes,
                    **(fetch_options or {}),
                )
                path = links.assemble(fetched, got.parts, lambda: False)
                name, home = f"{got.title}{path.suffix}", Path.cwd()
            else:
                path, name, home = item, item.name, item.parent
            checked = probe(path, settings.max_duration_s)
            if isinstance(item, str) and options.format is None:
                # A link becomes a file that plays everywhere unless something else was chosen.
                chosen = replace(options, format="mp4" if checked.kind == "video" else "m4a")
            result = pipeline.run(
                path,
                checked,
                chosen,
                functools.partial(separate_chunked, engine),
                lambda: False,
                progress,
                work,
                staging,
            )
            suffix = "" if options.keep_music else SUFFIX
            target = free_name(
                out_dir or home, download_name(name, pipeline.extension(result.format), suffix)
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staging / result.output, target)
            sys.stderr.write("\n")
            out(str(target))
            for note in result.notes:
                out(f"  {note}")
        # Anything else that goes wrong (an ffmpeg or engine error) fails this file, not the run.
        except Exception as exc:
            sys.stderr.write("\n")
            out(f"{label}: {getattr(exc, 'message', None) or exc}")
            failed += 1
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(fetched, ignore_errors=True)
    return 1 if failed else 0


def missing_libraries(name: str | None) -> str:
    return f"The separation libraries are not installed ({name}). Run: uv sync"


def ready_to_separate(models_dir: Path, preset: "Preset") -> bool:
    """Checks the separation libraries are installed, then downloads the model once, with progress.

    The libraries come first so a missing install doesn't cost a 913 MB download.
    """
    from sukoon import models
    from sukoon.download import download_preset

    missing = next((m for m in SEPARATION_MODULES if importlib.util.find_spec(m) is None), None)
    if missing:
        print(missing_libraries(missing), file=sys.stderr)
        return False
    if not models.is_ready(models_dir, preset):
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading the {preset} model once...", file=sys.stderr)

        def shown(done: int, total: int, rate: float) -> None:
            sys.stderr.write(f"\r{done / 1e6:7.1f} of {total / 1e6:.0f} MB  {rate / 1e6:5.1f} MB/s")

        download_preset(models_dir, preset, shown)
        sys.stderr.write("\n")
    return True


def run_clean(args: argparse.Namespace, settings: Settings) -> int:
    from sukoon.engine import AudioSeparatorEngine
    from sukoon.pipeline import Options

    models_dir = settings.area("models")
    if not args.keep_music and not ready_to_separate(models_dir, args.preset):
        return 1
    options = Options(
        preset=args.preset,
        device=args.device,
        format=args.format,
        track=None if args.track is None else args.track - 1,
        reencode_ok=args.allow_reencode,
        keep_music=args.keep_music,
    )
    return clean(
        [f if "://" in f else Path(f) for f in args.files],
        args.out and Path(args.out),
        options,
        AudioSeparatorEngine(models_dir),
        settings,
    )


def run_bench(args: argparse.Namespace, settings: Settings) -> int:
    from sukoon.bench import bench
    from sukoon.engine import AudioSeparatorEngine

    models_dir = settings.area("models")
    if not ready_to_separate(models_dir, args.preset):
        return 1
    try:
        bench(AudioSeparatorEngine(models_dir), args.preset, args.device)
    except ImportError as exc:
        print(missing_libraries(exc.name), file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # Git Bash hands Windows Python a cp1252 stdout, which can't print Arabic file names.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    browser = argparse.ArgumentParser(add_help=False)
    # SUPPRESS keeps the subcommand's copy from resetting a flag given before it.
    browser.add_argument(
        "--no-browser",
        action="store_true",
        default=argparse.SUPPRESS,
        help="don't open the browser",
    )
    parser = argparse.ArgumentParser(
        prog="sukoon", description="Remove the music, keep the voices.", parents=[browser]
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="start the app (the default)", parents=[browser])
    sub.add_parser("doctor", help="check ffmpeg, torch, disk space, and models")
    clean_p = sub.add_parser("clean", help="remove the music from files or links in the terminal")
    bench_p = sub.add_parser("bench", help="time separation on a 30 second clip")
    bench_p.add_argument("--preset", choices=["best", "fast"], default="best")
    bench_p.add_argument("--device", choices=["auto", "cpu"], default="auto")
    clean_p.add_argument("files", nargs="+", help="files, or links from the sites the app takes")
    clean_p.add_argument("--preset", choices=["best", "fast"], default="best")
    clean_p.add_argument("--device", choices=["auto", "cpu"], default="auto")
    clean_p.add_argument(
        "--format",
        choices=[*AUDIO_FORMATS, *VIDEO_CONTAINERS],
        help="output format (default: the same as the input)",
    )
    clean_p.add_argument(
        "--track", type=int, help="audio track number, from 1 (default: the track marked default)"
    )
    clean_p.add_argument(
        "--allow-reencode",
        action="store_true",
        help="re-encode the picture when the chosen container needs it",
    )
    clean_p.add_argument(
        "--keep-music", action="store_true", help="download only: convert, keep the music"
    )
    clean_p.add_argument(
        "--out", help="folder for the results (default: next to each file, or here for links)"
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if args.command == "doctor":
        return doctor.run(settings)
    if args.command == "clean":
        return run_clean(args, settings)
    if args.command == "bench":
        return run_bench(args, settings)
    return serve(settings, open_browser=not getattr(args, "no_browser", False))
