import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon.cli import bind_first_free, clean, main
from sukoon.engine import FakeEngine
from sukoon.pipeline import Options


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


def test_clean_writes_next_to_the_output_folder_and_prints_the_path(corpus, settings, tmp_path):
    printed = []
    code = clean(
        [corpus / "song-with-cover.mp3", corpus / "short-2s.wav"],
        tmp_path / "out",
        Options(preset="fast"),
        FakeEngine(),
        settings,
        out=printed.append,
    )
    assert code == 0
    assert printed == [
        str(tmp_path / "out" / "song-with-cover (no music).mp3"),
        str(tmp_path / "out" / "short-2s (no music).wav"),
    ]
    assert all(
        (tmp_path / "out" / n).stat().st_size > 1000
        for n in ("song-with-cover (no music).mp3", "short-2s (no music).wav")
    )
    assert list((settings.home / "work").iterdir()) == []
    assert list((settings.home / "outputs").iterdir()) == []


def test_clean_never_overwrites(corpus, settings, tmp_path):
    for _ in range(2):
        clean(
            [corpus / "short-2s.wav"],
            tmp_path,
            Options(),
            FakeEngine(),
            settings,
            out=lambda s: None,
        )
    assert sorted(p.name for p in tmp_path.glob("short-2s*")) == [
        "short-2s (no music) (2).wav",
        "short-2s (no music).wav",
    ]


def test_clean_reports_a_rejected_file_and_carries_on(corpus, settings, tmp_path):
    printed = []
    code = clean(
        [corpus / "video-no-audio.mp4", corpus / "short-2s.wav"],
        tmp_path,
        Options(),
        FakeEngine(),
        settings,
        out=printed.append,
    )
    assert code == 1
    assert printed[0] == (
        "video-no-audio.mp4: This video has no sound track, so there is nothing to clean."
    )
    assert printed[1].endswith("short-2s (no music).wav")


def test_clean_reports_an_engine_failure_and_carries_on(corpus, settings, tmp_path):
    printed = []
    code = clean(
        [corpus / "short-2s.wav", corpus / "mono-22k.wav"],
        tmp_path,
        Options(),
        FakeEngine(fail="raise", fail_on=1),
        settings,
        out=printed.append,
    )
    assert code == 1
    assert printed[0] == "short-2s.wav: fake engine failure"
    assert printed[1].endswith("mono-22k (no music).wav")


def test_clean_format_option(corpus, settings, tmp_path):
    printed = []
    clean(
        [corpus / "short-2s.wav"],
        tmp_path,
        Options(format="flac"),
        FakeEngine(),
        settings,
        out=printed.append,
    )
    assert printed == [str(tmp_path / "short-2s (no music).flac")]


def test_clean_reports_a_tampered_model_instead_of_crashing(corpus, settings, tmp_path):
    import hashlib

    from sukoon.engine import AudioSeparatorEngine
    from sukoon.models import CHECKSUM_MESSAGE, ModelFile

    body = b"weights" * 100
    files = (
        ModelFile(
            "fast",
            "UVR-MDX-NET-Voc_FT.onnx",
            "https://example.invalid/m",
            len(body),
            hashlib.sha256(body).hexdigest(),
        ),
    )
    (settings.area("models") / "UVR-MDX-NET-Voc_FT.onnx").write_bytes(body[:-1] + b"!")
    printed = []
    code = clean(
        [corpus / "short-2s.wav"],
        tmp_path,
        Options(preset="fast"),
        AudioSeparatorEngine(settings.area("models"), files),
        settings,
        out=printed.append,
    )
    assert code == 1
    assert printed == [CHECKSUM_MESSAGE]


def test_clean_video_keeps_the_container_and_track_option(corpus, settings, tmp_path):
    printed = []
    code = clean(
        [corpus / "two-tracks.mkv"],
        tmp_path,
        Options(track=1),
        FakeEngine(),
        settings,
        out=printed.append,
    )
    assert code == 0
    assert printed == [str(tmp_path / "two-tracks (no music).mkv")]


def test_clean_refuses_a_reencode_unless_allowed(corpus, settings, tmp_path):
    printed = []
    assert (
        clean(
            [corpus / "vp9-opus.webm"],
            tmp_path,
            Options(format="mov"),
            FakeEngine(),
            settings,
            out=printed.append,
        )
        == 1
    )
    assert "re-encoded to H.264" in printed[0]
    assert (
        clean(
            [corpus / "vp9-opus.webm"],
            tmp_path,
            Options(format="mov", reencode_ok=True),
            FakeEngine(),
            settings,
            out=lambda s: None,
        )
        == 0
    )


def test_clean_accepts_every_output_format(capsys):
    with pytest.raises(SystemExit):
        main(["clean", "--help"])
    assert "{mp3,m4a,wav,flac,opus,ogg,mp4,mkv,webm,mov}" in capsys.readouterr().out


@pytest.mark.parametrize("command", [["bench"], ["clean", "talk.mp3"]])
def test_missing_separation_libraries_are_reported_before_any_download(
    command, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("SUKOON_HOME", str(tmp_path))
    # How Python sees a package that isn't installed.
    monkeypatch.setitem(sys.modules, "torch", None)
    assert main(command) == 1
    assert "uv sync --extra cpu" in capsys.readouterr().err
    assert not any((tmp_path / "models").glob("*"))
