import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon.cli import bind_first_free, main


def free_port_pair():
    """Two consecutive free ports high enough not to collide with a running app."""
    for first in range(18417, 18600, 2):
        socks = []
        try:
            for p in (first, first + 1):
                s = socket.socket()
                s.bind(("127.0.0.1", p))
                socks.append(s)
            return first
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("no free ports")


def test_dummy_listener_pushes_to_next_port():
    first = free_port_pair()
    dummy = socket.socket()
    dummy.bind(("127.0.0.1", first))
    dummy.listen()
    try:
        sock, port = bind_first_free(first, first + 1)
        assert port == first + 1
        assert sock is not None
        sock.close()
    finally:
        dummy.close()


def test_running_sukoon_is_reused():
    first = free_port_pair()

    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "ok", "app": "sukoon", "version": "0.1.0"}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", first), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert bind_first_free(first, first + 1) == (None, first)
    finally:
        server.shutdown()
        server.server_close()


def test_all_ports_busy_is_a_clear_error():
    first = free_port_pair()
    held = []
    for p in (first, first + 1):
        s = socket.socket()
        s.bind(("127.0.0.1", p))
        s.listen()
        held.append(s)
    try:
        with pytest.raises(SystemExit, match="all in use"):
            bind_first_free(first, first + 1)
    finally:
        for s in held:
            s.close()


def test_clean_stub_says_not_implemented(capsys):
    assert main(["clean", "a.mp3"]) == 2
    assert "not implemented" in capsys.readouterr().err
