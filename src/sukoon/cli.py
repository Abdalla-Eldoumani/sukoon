import argparse
import functools
import json
import shutil
import socket
import sys
import urllib.request
import uuid
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from sukoon import doctor
from sukoon.settings import Settings

if TYPE_CHECKING:
    from sukoon.engine import Engine
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
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
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
    files: Sequence[Path],
    out_dir: Path | None,
    options: "Options",
    engine: "Engine",
    settings: Settings,
    out: Callable[[str], None] = print,
) -> int:
    """The browser's pipeline, run from the terminal one file at a time. 1 if any file failed."""
    from sukoon import pipeline
    from sukoon.chunk import separate_chunked
    from sukoon.errors import JobError
    from sukoon.models import ModelChecksumError, ModelMissingError
    from sukoon.naming import download_name
    from sukoon.probe import Rejected, probe

    settings.ensure_dirs()
    try:
        engine.prepare(options.preset, options.device)
    except (ModelChecksumError, ModelMissingError, ImportError) as exc:
        out(str(exc))
        return 1
    failed = 0
    for path in files:
        job = str(uuid.uuid4())
        work, staging = settings.job_path("work", job), settings.job_path("outputs", job)

        def progress(
            stage: str, fraction: float, done: int, total: int, name: str = path.name
        ) -> None:
            sys.stderr.write(f"\r{name}  {stage.capitalize():<10} {fraction * 100:5.1f}%")
            sys.stderr.flush()

        try:
            result = pipeline.run(
                path,
                probe(path, settings.max_duration_s),
                options,
                functools.partial(separate_chunked, engine),
                lambda: False,
                progress,
                work,
                staging,
            )
            target = free_name(
                out_dir or path.parent, download_name(path.name, pipeline.extension(result.format))
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staging / result.output, target)
            sys.stderr.write("\n")
            out(str(target))
            for note in result.notes:
                out(f"  {note}")
        except (Rejected, JobError, OSError) as exc:
            sys.stderr.write("\n")
            out(f"{path.name}: {getattr(exc, 'message', None) or exc}")
            failed += 1
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return 1 if failed else 0


def run_clean(args: argparse.Namespace, settings: Settings) -> int:
    from sukoon import models
    from sukoon.download import download_preset
    from sukoon.engine import AudioSeparatorEngine
    from sukoon.pipeline import Options

    models_dir = settings.area("models")
    if not models.is_ready(models_dir, args.preset):
        print(f"Downloading the {args.preset} model once...", file=sys.stderr)

        def shown(done: int, total: int, rate: float) -> None:
            sys.stderr.write(f"\r{done / 1e6:7.1f} of {total / 1e6:.0f} MB  {rate / 1e6:5.1f} MB/s")

        download_preset(models_dir, args.preset, shown)
        sys.stderr.write("\n")
    options = Options(
        preset=args.preset,
        device=args.device,
        format=args.format,
        track=None if args.track is None else args.track - 1,
        reencode_ok=args.allow_reencode,
    )
    return clean(
        [Path(f) for f in args.files],
        args.out and Path(args.out),
        options,
        AudioSeparatorEngine(models_dir),
        settings,
    )


def main(argv: Sequence[str] | None = None) -> int:
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
    clean_p = sub.add_parser("clean", help="remove the music from files in the terminal")
    clean_p.add_argument("files", nargs="+")
    clean_p.add_argument("--preset", choices=["best", "fast"], default="best")
    clean_p.add_argument("--device", choices=["auto", "cpu"], default="auto")
    clean_p.add_argument(
        "--format",
        choices=["mp3", "m4a", "wav", "flac", "opus", "ogg"],
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
    clean_p.add_argument("--out", help="folder for the results (default: next to each input)")
    args = parser.parse_args(argv)

    settings = Settings()
    if args.command == "doctor":
        return doctor.run(settings)
    if args.command == "clean":
        return run_clean(args, settings)
    return serve(settings, open_browser=not getattr(args, "no_browser", False))
