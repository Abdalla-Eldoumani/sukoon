import socket
import subprocess
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


MPD = """<?xml version="1.0" encoding="UTF-8"?>{lead}
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT2S"
     profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" minBufferTime="PT1S">
  <Period>
    <AdaptationSet mimeType="audio/mp4" contentType="audio">
      <Representation id="a" bandwidth="128000" codecs="mp4a.40.2" audioSamplingRate="44100">
        <BaseURL>{target}</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
"""
# Pushes <MPD past the first bytes of the file; ffmpeg still finds it up to a megabyte in.
SHORT_COMMENT = "<!--" + " " * 200 + "-->"
LONG_COMMENT = "<!--" + " " * 300_000 + "-->"


@pytest.fixture
def other_file(tmp_path, corpus):
    """A real media file the manifest points at; reading it is the leak."""
    path = tmp_path / "other.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(corpus / "short-2s.wav"), "-c:a", "aac", str(path)],
        check=True,
    )
    return path


@pytest.mark.parametrize(
    "lead", ["", SHORT_COMMENT, LONG_COMMENT], ids=["plain", "padded", "padded-deep"]
)
def test_dash_manifest_pointing_at_a_local_file_is_rejected(tmp_path, other_file, lead):
    manifest = tmp_path / "upload.mp3"
    manifest.write_text(MPD.format(lead=lead, target=other_file.as_uri()))
    with pytest.raises(Rejected) as err:
        probe(manifest)
    assert err.value.message == PLAYLIST


@pytest.mark.parametrize("lead", ["", LONG_COMMENT], ids=["plain", "padded-deep"])
def test_dash_manifest_pointing_at_the_network_makes_no_request(tmp_path, lead):
    listener = Listener()
    try:
        manifest = tmp_path / "upload.mp3"
        manifest.write_text(MPD.format(lead=lead, target=f"http://127.0.0.1:{listener.port}/a.m4a"))
        with pytest.raises(Rejected):
            probe(manifest)
    finally:
        listener.close()
    assert listener.connections == 0


def test_dash_manifest_upload_is_refused_and_deleted(client, settings, tmp_path, other_file):
    manifest = tmp_path / "upload.mp3"
    manifest.write_text(MPD.format(lead="", target=other_file.as_uri()))
    job = upload(client, manifest).json()
    assert job["state"] == "failed"
    assert job["error"] == PLAYLIST
    assert not (settings.home / "uploads" / job["id"]).exists()


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
