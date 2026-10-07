"""`sukoon clean` and `sukoon bench`: the browser's pipeline, run from the terminal."""

import argparse
import functools
import importlib.util
import shutil
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sukoon.settings import Settings

if TYPE_CHECKING:
    from sukoon.jobs.pipeline import Options
    from sukoon.separation.engine import Engine
    from sukoon.separation.models import Preset

SEPARATION_MODULES = ("torch", "audio_separator")


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
    """Runs each file or link through the pipeline, one at a time.

    Returns 1 if anything failed. A link is fetched first and its result lands in `out_dir`,
    or the current folder.
    """
    from sukoon.jobs import pipeline
    from sukoon.links.fetch import assemble, fetch
    from sukoon.links.sites import site
    from sukoon.media.naming import SUFFIX, download_name
    from sukoon.media.probe import probe
    from sukoon.separation.chunk import separate_chunked
    from sukoon.separation.models import ModelChecksumError, ModelMissingError

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
                site(item)
                got = fetch(
                    item,
                    fetched,
                    fetching,
                    lambda: False,
                    settings.max_duration_s,
                    settings.max_upload_bytes,
                    **(fetch_options or {}),
                )
                path = assemble(fetched, got.parts, lambda: False)
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
    from sukoon.separation import models
    from sukoon.separation.download import download_preset

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
    from sukoon.jobs.pipeline import Options
    from sukoon.separation.engine import AudioSeparatorEngine

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
    from sukoon.separation.bench import bench
    from sukoon.separation.engine import AudioSeparatorEngine

    models_dir = settings.area("models")
    if not ready_to_separate(models_dir, args.preset):
        return 1
    try:
        bench(AudioSeparatorEngine(models_dir), args.preset, args.device)
    except ImportError as exc:
        print(missing_libraries(exc.name), file=sys.stderr)
        return 1
    return 0
