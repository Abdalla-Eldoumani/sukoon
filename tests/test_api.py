import hashlib
import json
import shutil
import socket
import threading
import time
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from sukoon.models import ModelFile
from sukoon.probe import NO_SOUND, PLAYLIST, UNREADABLE
from tests.conftest import BASE, fake_app

FINISHED = {"done", "failed", "canceled", "interrupted", "awaiting_track", "waiting_model"}


def upload(client, path, name=None, **params):
    with open(path, "rb") as f:
        r = client.post(
            "/api/jobs",
            params=params,
            files={"file": (name or path.name, f, "application/octet-stream")},
        )
    return r


def wait(client, job_id, states=FINISHED, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in states:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job stuck in {job['state']}")


def test_upload_runs_to_done_and_offers_the_download(client, corpus, tmp_path):
    r = upload(client, corpus / "song-with-cover.mp3", name="My song.mp3", preset="fast")
    assert r.status_code == 201
    job = wait(client, r.json()["id"])
    assert job["state"] == "done", job
    assert job["kind"] == "audio"
    assert job["output_name"] == "My song (no music).mp3"
    d = client.get(f"/api/jobs/{job['id']}/output")
    assert d.status_code == 200
    assert d.headers["content-disposition"] == (
        'attachment; filename="My song (no music).mp3"; '
        "filename*=UTF-8''My%20song%20%28no%20music%29.mp3"
    )
    out = tmp_path / "out.mp3"
    out.write_bytes(d.content)
    assert out.stat().st_size > 10_000


def test_files_on_disk_use_generated_names_only(client, corpus, settings):
    r = upload(client, corpus / "short-2s.wav", name="../../evil name.wav")
    job = wait(client, r.json()["id"])
    assert job["state"] == "done"
    names = {p.name for p in settings.home.rglob("*") if p.is_file()}
    assert not any("evil" in n for n in names)
    assert (settings.home / "uploads" / job["id"] / "source.wav").is_file()


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("empty.mp4", UNREADABLE),
        ("text-renamed.mp4", UNREADABLE),
        ("random-bytes.bin", UNREADABLE),
        ("video-no-audio.mp4", NO_SOUND),
        ("playlist-local.m3u8", PLAYLIST),
        ("playlist-remote.m3u8", PLAYLIST),
    ],
)
def test_bad_files_are_rejected_with_a_sentence_and_deleted(
    client, corpus, settings, name, message
):
    r = upload(client, corpus / name)
    assert r.status_code == 201
    job = r.json()
    assert job["state"] == "failed"
    assert job["error"] == message
    assert job["retryable"] is False
    assert not (settings.home / "uploads" / job["id"]).exists()


def test_several_audio_tracks_wait_for_a_choice(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    assert job["state"] == "awaiting_track"
    assert [t["language"] for t in job["tracks"]] == ["eng", "ara"]


def test_too_big_is_refused_before_reading(settings, corpus, web_dist):
    from dataclasses import replace

    small = replace(settings, max_upload_bytes=1000)
    with TestClient(fake_app(small, web_dist=web_dist), base_url=BASE) as client:
        r = upload(client, corpus / "short-2s.wav")
    assert r.status_code == 413
    assert "bigger than" in r.json()["error"]


def test_full_queue_is_refused(settings, corpus, web_dist):
    from dataclasses import replace

    tiny = replace(settings, max_queued=1)
    with TestClient(
        fake_app(tiny, web_dist=web_dist, model_ready=lambda p: False), base_url=BASE
    ) as client:
        first = upload(client, corpus / "short-2s.wav").json()
        wait(client, first["id"])
        r = upload(client, corpus / "short-2s.wav")
    assert r.status_code == 429
    assert r.json()["error"] == "The queue is full (1 files). Add more once some have finished."


def test_low_disk_is_refused(client, corpus, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(10**9, 10**9, 10**6))
    r = upload(client, corpus / "short-2s.wav")
    assert r.status_code == 507
    assert r.json()["error"] == "There isn't enough free disk space for this file."


def test_unknown_preset_or_format(client, corpus):
    assert upload(client, corpus / "short-2s.wav", preset="ultra").status_code == 400
    assert upload(client, corpus / "short-2s.wav", format="exe").status_code == 400


def test_chosen_format_is_used(client, corpus):
    job = upload(client, corpus / "short-2s.wav", format="flac").json()
    job = wait(client, job["id"])
    assert job["output_name"] == "short-2s (no music).flac"


def test_output_is_404_until_done(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    assert client.get(f"/api/jobs/{job['id']}/output").status_code == 404
    assert client.get("/api/jobs/8a6f0c2e-2a8b-4f3e-9d61-2b1f4c9e7a10").status_code == 404


def test_writes_from_another_site_are_refused(client, corpus):
    with open(corpus / "short-2s.wav", "rb") as f:
        r = client.post(
            "/api/jobs", files={"file": ("a.wav", f)}, headers={"origin": "https://evil.example"}
        )
    assert r.status_code == 403
    assert client.get("/api/jobs").json() == []


def test_jobs_list_in_drop_order(client, corpus):
    ids = [
        upload(client, corpus / n).json()["id"]
        for n in ("short-2s.wav", "mono-22k.wav", "empty.mp4")
    ]
    assert [j["id"] for j in client.get("/api/jobs").json()] == ids


def read_events(url, count, timeout=20):
    """Reads `count` server-sent events from a live server."""
    events = []
    with httpx.stream("GET", f"{url}/api/events", timeout=timeout) as r:
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[6:])))
                if len(events) >= count:
                    break
    return events


def test_events_start_with_a_snapshot_then_follow_changes(live, corpus):
    server = live()
    with httpx.Client(base_url=server.url) as client:
        job = upload(client, corpus / "short-2s.wav").json()
        wait(client, job["id"])
        events = read_events(server.url, 1)
        assert events[0][0] == "snapshot"
        assert [j["id"] for j in events[0][1]["jobs"]] == [job["id"]]
        assert events[0][1]["jobs"][0]["state"] == "done"
        assert [m["preset"] for m in events[0][1]["models"]] == ["best", "fast"]

        got = []
        reader = threading.Thread(target=lambda: got.extend(read_events(server.url, 6)))
        reader.start()
        time.sleep(0.5)
        upload(client, corpus / "short-2s.wav")
        reader.join(timeout=30)
    states = [data["state"] for event, data in got[1:] if event == "job"]
    assert states[0] == "checking"
    assert "queued" in states


def test_aborted_upload_leaves_nothing_behind(live, settings, corpus):
    server = live()
    body = (corpus / "speech-over-music-30s.wav").read_bytes()
    boundary = "sukoonboundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n\r\n'
    ).encode()
    sock = socket.create_connection(("127.0.0.1", server.port))
    sock.sendall(
        f"POST /api/jobs HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(head) + len(body) + 100}\r\n\r\n".encode()
        + head
        + body[:200_000]
    )
    time.sleep(0.5)
    sock.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        jobs = httpx.get(f"{server.url}/api/jobs").json()
        leftovers = list((settings.home / "uploads").rglob("*"))
        if not jobs and not leftovers:
            break
        time.sleep(0.1)
    assert jobs == []
    assert leftovers == []


BODY = b"pretend fast model " * 5000
FILES = (
    ModelFile("fast", "UVR-MDX-NET-Voc_FT.onnx", "", len(BODY), hashlib.sha256(BODY).hexdigest()),
)


@pytest.fixture
def model_source():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    from dataclasses import replace

    yield (replace(FILES[0], url=f"http://127.0.0.1:{httpd.server_address[1]}/m.onnx"),)
    httpd.shutdown()
    httpd.server_close()


def test_job_waits_for_its_model_and_runs_once_downloaded(settings, corpus, web_dist, model_source):
    app = fake_app(
        settings, web_dist=web_dist, model_ready=None, worker={"model_files": model_source}
    )
    with TestClient(app, base_url=BASE) as client:
        models = client.get("/api/models").json()
        assert [(m["preset"], m["ready"]) for m in models] == [("best", True), ("fast", False)]
        job = upload(client, corpus / "short-2s.wav", preset="fast").json()
        assert wait(client, job["id"])["state"] == "waiting_model"
        assert client.post("/api/models/fast/download").status_code == 200
        assert wait(client, job["id"], {"done", "failed"})["state"] == "done"
        assert client.get("/api/models").json()[1]["ready"] is True


def test_start_with_fast_moves_waiting_jobs_to_fast(settings, corpus, web_dist, model_source):
    missing_best = ModelFile(
        "best", "vocals_mel_band_roformer.ckpt", "http://127.0.0.1:1/x", 10, "0" * 64
    )
    app = fake_app(
        settings,
        web_dist=web_dist,
        model_ready=None,
        worker={"model_files": (*model_source, missing_best)},
    )
    with TestClient(app, base_url=BASE) as client:
        job = upload(client, corpus / "short-2s.wav").json()
        assert wait(client, job["id"])["state"] == "waiting_model"
        client.post("/api/models/fast/download", params={"switch": "1"})
        done = wait(client, job["id"], {"done", "failed"})
    assert done["state"] == "done"
    assert done["options"]["preset"] == "fast"


def test_malformed_upload_leaves_no_job_and_no_file(client, settings):
    boundary = "b0undary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"'
        f"\r\n\r\n" + "x" * 5000 + f"\r\n--{boundary}\r\nBroken header line without colon"
        f"\r\n\r\nmore\r\n--{boundary}--\r\n"
    ).encode()
    r = client.post(
        "/api/jobs",
        content=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    assert r.status_code == 400
    assert client.get("/api/jobs").json() == []
    assert list((settings.home / "uploads").iterdir()) == []


def test_cancel_a_queued_job_and_cancel_twice(settings, corpus, web_dist):
    with TestClient(
        fake_app(settings, web_dist=web_dist, model_ready=lambda p: False), base_url=BASE
    ) as client:
        job = upload(client, corpus / "short-2s.wav").json()
        wait(client, job["id"])
        first = client.post(f"/api/jobs/{job['id']}/cancel")
        second = client.post(f"/api/jobs/{job['id']}/cancel")
    assert first.json()["state"] == "canceled"
    assert second.status_code == 200
    assert second.json()["state"] == "canceled"


def test_cancel_a_finished_job_changes_nothing(client, corpus):
    job = wait(client, upload(client, corpus / "short-2s.wav").json()["id"])
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["state"] == "done"


def test_event_stream_sends_keep_alives(live, monkeypatch):
    monkeypatch.setattr("sukoon.api.KEEPALIVE_S", 0.2)
    server = live()
    lines = []
    with httpx.stream("GET", f"{server.url}/api/events", timeout=10) as r:
        for line in r.iter_lines():
            lines.append(line)
            if line == ": keep-alive":
                break
    assert lines[0] == "event: snapshot"
    assert lines[-1] == ": keep-alive"


def test_track_choice_continues_the_job(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    assert job["state"] == "awaiting_track"
    assert job["options"]["format"] == "mkv"
    r = client.post(f"/api/jobs/{job['id']}/choose", json={"track": 1})
    assert r.json()["state"] == "queued"
    done = wait(client, job["id"], {"done", "failed"})
    assert done["state"] == "done"
    assert done["options"]["track"] == 1
    assert done["output_name"] == "two-tracks (no music).mkv"


def test_bad_track_is_refused(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    assert client.post(f"/api/jobs/{job['id']}/choose", json={"track": 5}).status_code == 400


def test_reencode_waits_for_a_confirm(client, corpus, tmp_path):
    job = upload(client, corpus / "vp9-opus.webm", format="mov").json()
    assert job["state"] == "awaiting_confirm"
    assert job["confirm"].startswith("The picture will be re-encoded to H.264 for MOV")
    assert {f["value"]: f["reencode"] for f in job["formats"] if f["video"]} == {
        "mp4": False,
        "mkv": False,
        "webm": False,
        "mov": True,
    }
    r = client.post(f"/api/jobs/{job['id']}/choose", json={"confirm": True})
    assert r.json()["state"] == "queued"
    done = wait(client, job["id"], {"done", "failed"})
    assert done["output_name"] == "vp9-opus (no music).mov"


def test_switching_away_from_a_reencode_needs_no_confirm(client, corpus):
    job = upload(client, corpus / "vp9-opus.webm", format="mov").json()
    r = client.post(f"/api/jobs/{job['id']}/choose", json={"format": "mkv"})
    assert r.json()["state"] == "queued"
    assert r.json()["confirm"] is None


def test_choosing_after_the_job_ran_is_refused(client, corpus):
    job = wait(client, upload(client, corpus / "offset-0.5s.mp4").json()["id"])
    assert job["output_name"] == "offset-0.5s (no music).mp4"
    assert client.post(f"/api/jobs/{job['id']}/choose", json={"format": "mkv"}).status_code == 409


def test_audio_file_offers_audio_formats_only(client, corpus):
    job = upload(client, corpus / "short-2s.wav").json()
    assert [f["value"] for f in job["formats"]] == ["mp3", "m4a", "wav", "flac", "opus", "ogg"]


def test_format_change_keeps_the_track_question_open(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    r = client.post(f"/api/jobs/{job['id']}/choose", json={"format": "webm"})
    assert r.json()["state"] == "awaiting_track"
    r = client.post(f"/api/jobs/{job['id']}/choose", json={"track": 1})
    assert r.json()["state"] == "awaiting_confirm"
    assert r.json()["options"]["format"] == "webm"
