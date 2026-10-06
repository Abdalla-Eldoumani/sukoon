import argparse
import json
import socket
import sys
import urllib.request
import webbrowser
from collections.abc import Sequence

from sukoon import doctor
from sukoon.settings import Settings


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
    args = parser.parse_args(argv)

    settings = Settings()
    if args.command == "doctor":
        return doctor.run(settings)
    if args.command == "clean":
        print("clean is not implemented yet.", file=sys.stderr)
        return 2
    return serve(settings, open_browser=not getattr(args, "no_browser", False))
