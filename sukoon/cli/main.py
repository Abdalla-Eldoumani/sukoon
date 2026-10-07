"""The `sukoon` command: its options, and which command runs."""

import argparse
import io
import sys
from collections.abc import Sequence

from sukoon.cli import doctor
from sukoon.cli.clean import run_bench, run_clean
from sukoon.cli.serve import serve
from sukoon.media.compat import VIDEO_CONTAINERS
from sukoon.media.encode import AUDIO_FORMATS
from sukoon.settings import Settings


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
