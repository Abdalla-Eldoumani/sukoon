import socket
import threading
import uuid

import pytest

from sukoon.media.probe import PLAYLIST, Rejected, probe
from sukoon.settings import Settings, UnsafePathError
from tests.test_api import upload, wait

JOB = "8a6f0c2e-2a8b-4f3e-9d61-2b1f4c9e7a10"
WRITES = [
    ("post", "/api/jobs"),
    ("post", f"/api/jobs/{JOB}/cancel"),
    ("post", f"/api/jobs/{JOB}/choose"),
    ("post", f"/api/jobs/{JOB}/retry"),
    ("delete", f"/api/jobs/{JOB}"),
    ("put", "/api/settings"),
    ("post", "/api/library/clear"),
    ("post", "/api/library/open"),
    ("post", "/api/models/fast/download"),
]


class Listener:
    """A TCP port that records every connection made to it."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self.running = True
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.connections += 1
            conn.close()

    def close(self):
        self.running = False
        self.thread.join(timeout=2)
        self.sock.close()


@pytest.mark.parametrize("magic", [True, False])
def test_playlist_pointing_at_the_network_makes_no_request(tmp_path, magic):
    listener = Listener()
    try:
        body = f"#EXTINF:5.0,\nhttp://127.0.0.1:{listener.port}/segment.ts\n#EXT-X-ENDLIST\n"
        header = "#EXTM3U\n#EXT-X-TARGETDURATION:5\n" if magic else "\n"
        playlist = tmp_path / "list.m3u8"
        playlist.write_text(header + body)
        with pytest.raises(Rejected):
            probe(playlist)
    finally:
        listener.close()
    assert listener.connections == 0


def test_playlist_pointing_at_local_files_is_rejected(corpus):
    with pytest.raises(Rejected) as err:
        probe(corpus / "playlist-local.m3u8")
    assert err.value.message == PLAYLIST


def test_playlist_upload_makes_no_request(client, tmp_path):
    listener = Listener()
    try:
        playlist = tmp_path / "list.m3u8"
        playlist.write_text(f"#EXTM3U\n#EXTINF:5.0,\nhttp://127.0.0.1:{listener.port}/a.ts\n")
        job = upload(client, playlist).json()
    finally:
        listener.close()
    assert job["error"] == PLAYLIST
    assert listener.connections == 0


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_every_write_refuses_a_foreign_origin(client, method, path):
    r = getattr(client, method)(path, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_every_write_refuses_a_foreign_host(client, method, path):
    r = getattr(client, method)(path, headers={"host": "evil.example:8417"})
    assert r.status_code == 400


def test_refused_writes_change_nothing(client, corpus):
    job = wait(client, upload(client, corpus / "short-2s.wav").json()["id"])
    evil = {"origin": "https://evil.example"}
    client.delete(f"/api/jobs/{job['id']}", headers=evil)
    client.post("/api/library/clear", headers=evil)
    client.put("/api/settings", json={"preset": "fast"}, headers=evil)
    assert client.get(f"/api/jobs/{job['id']}").json()["state"] == "done"
    assert client.get("/api/settings").json()["preset"] == "best"


@pytest.mark.parametrize("bad", ["../uploads", "..%2f..%2fetc", "/etc/passwd", "nope"])
def test_job_routes_refuse_ids_that_are_not_uuids(client, bad):
    assert client.get(f"/api/jobs/{bad}/output").status_code in (404, 422)


def test_path_helper_refuses_traversal(tmp_path):
    s = Settings(home=tmp_path)
    for bad in ("../x", "../../" + str(uuid.uuid4()), str(uuid.uuid4()) + "/..", "."):
        with pytest.raises(UnsafePathError):
            s.job_path("outputs", bad)
