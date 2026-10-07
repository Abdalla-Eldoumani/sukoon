"""`sukoon` with no command: start the app on the first free port, or open the one running."""

import json
import socket
import sys
import urllib.request
import webbrowser

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

    from sukoon.separation.device import detect_cached
    from sukoon.server.app import create_app

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
