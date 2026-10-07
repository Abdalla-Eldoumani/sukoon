import json
import os
import subprocess
import sys
import threading
import time

import httpx
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from sukoon.jobs.store import Store
from sukoon.separation.worker import Worker, WorkerConfig
from tests.conftest import BASE, fake_app, fixture_script
from tests.test_api import upload, wait

RUNNING = {"decoding", "separating", "encoding"}
END = {"done", "failed", "canceled", "interrupted"}


@pytest.fixture(scope="module")
def long_mix(tmp_path_factory, corpus):
    """Five minutes of the speech-over-music mix: six chunks."""
    out = tmp_path_factory.mktemp("long") / "five-minutes.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-stream_loop",
            "9",
            "-i",
            str(corpus / "speech-over-music-30s.wav"),
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
    )
    return out


def events_until(url, done, timeout=60):
    """Reads the event stream until done(events) is true; returns the parsed events."""
    events = []
    with httpx.stream("GET", f"{url}/api/events", timeout=timeout) as r:
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
                if done(events):
                    break
    return events


def test_twelve_files_queue_in_order_and_run_one_at_a_time(live, corpus):
    server = live(fake={"delay": 0.2})
    names = ["short-2s.wav"] * 5 + ["text-renamed.mp4"] + ["mono-22k.wav"] * 6
    seen = []
    reader = threading.Thread(
        target=lambda: seen.extend(
            events_until(
                server.url,
                lambda ev: sum(1 for n, d in ev if n == "job" and d["state"] == "done") >= 11,
                timeout=120,
            )
        )
    )
    reader.start()
    time.sleep(0.5)
    with httpx.Client(base_url=server.url) as client:
        ids = [
            upload(client, corpus / n, name=f"{i:02d}-{n}").json()["id"]
            for i, n in enumerate(names)
        ]
        reader.join(timeout=120)
        jobs = client.get("/api/jobs").json()
    assert [j["id"] for j in jobs] == ids
    assert [j["state"] for j in jobs] == ["done"] * 5 + ["failed"] + ["done"] * 6
    running, peak, finished = set(), 0, []
    for name, data in seen:
        if name != "job":
            continue
        if data["state"] in RUNNING:
            running.add(data["id"])
        else:
            running.discard(data["id"])
        if data["state"] == "done" and data["id"] not in finished:
            finished.append(data["id"])
        peak = max(peak, len(running))
    assert peak == 1
    assert finished == [i for i, n in zip(ids, names, strict=True) if n != "text-renamed.mp4"]


def test_cancel_while_separating_lands_within_one_chunk(settings, web_dist, long_mix):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"delay": 1.0}), base_url=BASE
    ) as client:
        job = upload(client, long_mix).json()
        wait(client, job["id"], {"separating"})
        while client.get(f"/api/jobs/{job['id']}").json()["eta"] is None:
            time.sleep(0.05)
        started = time.monotonic()
        client.post(f"/api/jobs/{job['id']}/cancel")
        final = wait(client, job["id"], END)
        took = time.monotonic() - started
    assert final["state"] == "canceled"
    assert took < 2.5  # one chunk is about a second
    assert not (settings.home / "work" / job["id"]).exists()
    assert not (settings.home / "outputs" / job["id"]).exists()


def test_hung_engine_is_terminated_and_replaced(settings, web_dist, corpus):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"fail": "hang"}), base_url=BASE
    ) as client:
        hung = upload(client, corpus / "short-2s.wav").json()
        wait(client, hung["id"], {"separating"})
        started = time.monotonic()
        client.post(f"/api/jobs/{hung['id']}/cancel")
        final = wait(client, hung["id"], END, timeout=40)
        took = time.monotonic() - started
        # The replacement worker starts with a fresh engine whose first call hangs again,
        # so the next job proves the replacement exists by reaching the separating stage.
        nxt = upload(client, corpus / "short-2s.wav").json()
        reached = wait(client, nxt["id"], {"separating"})["state"]
        client.post(f"/api/jobs/{nxt['id']}/cancel")
        wait(client, nxt["id"], END, timeout=40)
    assert final["state"] == "canceled"
    assert took < 25
    assert reached == "separating"


def test_retry_after_failure_and_after_cancel(settings, web_dist, corpus):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"fail": "raise"}), base_url=BASE
    ) as client:
        job = upload(client, corpus / "short-2s.wav").json()
        failed = wait(client, job["id"], END)
        assert failed["state"] == "failed"
        assert failed["error"] == "The separation failed: fake engine failure"
        assert client.post(f"/api/jobs/{job['id']}/retry").json()["state"] in {"queued", *RUNNING}
        assert wait(client, job["id"], END)["state"] == "done"
    with TestClient(
        fake_app(settings, web_dist=web_dist, model_ready=lambda p: False), base_url=BASE
    ) as client:
        job = upload(client, corpus / "short-2s.wav").json()
        wait(client, job["id"])
        client.post(f"/api/jobs/{job['id']}/cancel")
        assert client.post(f"/api/jobs/{job['id']}/retry").json()["state"] == "queued"


def test_rejected_and_done_jobs_cannot_be_retried(client, corpus):
    bad = upload(client, corpus / "empty.mp4").json()
    assert client.post(f"/api/jobs/{bad['id']}/retry").status_code == 409
    done = wait(client, upload(client, corpus / "short-2s.wav").json()["id"])
    assert client.post(f"/api/jobs/{done['id']}/retry").status_code == 409


def test_delete_removes_every_file(client, corpus, settings):
    job = wait(client, upload(client, corpus / "short-2s.wav").json()["id"])
    assert (settings.home / "outputs" / job["id"]).exists()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    for area in ("uploads", "work", "outputs"):
        assert not (settings.home / area / job["id"]).exists()


def test_running_job_must_be_canceled_before_delete(settings, web_dist, long_mix):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"delay": 1.0}), base_url=BASE
    ) as client:
        job = upload(client, long_mix).json()
        wait(client, job["id"], {"separating"})
        r = client.delete(f"/api/jobs/{job['id']}")
        client.post(f"/api/jobs/{job['id']}/cancel")
        wait(client, job["id"], END)
        assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert r.status_code == 409
    assert r.json()["detail"] == "Cancel this job before deleting it."


def test_restart_interrupts_running_jobs_and_sweeps_leftovers(settings, web_dist, corpus):
    store = Store(settings.db_path)
    job = store.create("talk.wav", {"preset": "best", "format": "wav"})
    folder = settings.home / "uploads" / job["id"]
    folder.mkdir(parents=True)
    (folder / "source.wav").write_bytes((corpus / "short-2s.wav").read_bytes())
    from sukoon.media.probe import probe

    store.update(job["id"], probe=probe(folder / "source.wav").to_json(), kind="audio")
    for state in ("queued", "decoding", "separating"):
        store.transition(job["id"], state)
    lost = store.create("half.wav", {"preset": "best"})  # checking, upload never finished
    unprobed = store.create("whole.wav", {"preset": "best"})  # uploaded, never checked
    (settings.home / "uploads" / unprobed["id"]).mkdir(parents=True)
    (settings.home / "uploads" / unprobed["id"] / "source.wav").write_bytes(b"x" * 10)
    store.close()
    stale_output = settings.home / "outputs" / job["id"] / ".output.wav.part"
    stale_output.parent.mkdir(parents=True)
    stale_output.write_bytes(b"x")
    os.utime(stale_output, (time.time() - 7200, time.time() - 7200))
    scratch = settings.home / "work" / job["id"]
    scratch.mkdir(parents=True)
    (scratch / "mixture.wav").write_bytes(b"x" * 100)
    old_part = settings.home / "models" / "model.onnx.part"
    old_part.write_bytes(b"x")
    os.utime(old_part, (time.time() - 7200, time.time() - 7200))
    fresh_part = settings.home / "models" / "other.onnx.part"
    fresh_part.write_bytes(b"x")

    with TestClient(fake_app(settings, web_dist=web_dist), base_url=BASE) as client:
        after = client.get(f"/api/jobs/{job['id']}").json()
        half = client.get(f"/api/jobs/{lost['id']}").json()
        assert after["state"] == "interrupted"
        assert not scratch.exists()
        assert not old_part.exists()
        assert fresh_part.exists()
        assert half["state"] == "failed"
        assert half["retryable"] is False
        never_checked = client.get(f"/api/jobs/{unprobed['id']}").json()
        assert never_checked["state"] == "failed"
        assert never_checked["retryable"] is False
        assert not (settings.home / "uploads" / unprobed["id"]).exists()
        assert not stale_output.exists()
        client.post(f"/api/jobs/{job['id']}/retry")
        assert wait(client, job["id"], END)["state"] == "done"


def test_stopping_the_app_interrupts_the_running_job(settings, web_dist, long_mix):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"delay": 1.0}), base_url=BASE
    ) as client:
        job = upload(client, long_mix).json()
        wait(client, job["id"], {"separating"})
    store = Store(settings.db_path)
    assert store.get(job["id"])["state"] == "interrupted"
    store.close()


def test_two_event_clients_see_the_same_sequence(live, corpus):
    server = live()
    streams = [[], []]

    def read(i):
        streams[i].extend(
            events_until(
                server.url, lambda ev: any(n == "job" and d["state"] == "done" for n, d in ev)
            )
        )

    readers = [threading.Thread(target=read, args=(i,)) for i in range(2)]
    for r in readers:
        r.start()
    time.sleep(0.5)
    with httpx.Client(base_url=server.url) as client:
        upload(client, corpus / "short-2s.wav")
    for r in readers:
        r.join(timeout=60)
    sequences = [[(d["state"], d["progress"]) for n, d in s if n == "job"] for s in streams]
    assert sequences[0] == sequences[1]
    assert sequences[0][-1][0] == "done"


def test_eta_is_close_to_the_real_remaining_time(settings, web_dist, long_mix):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"delay": 1.0}), base_url=BASE
    ) as client:
        job = upload(client, long_mix).json()
        wait(client, job["id"], {"separating"})
        while (eta := client.get(f"/api/jobs/{job['id']}").json()["eta"]) is None:
            time.sleep(0.02)
        started = time.monotonic()
        wait(client, job["id"], END)
        actual = time.monotonic() - started
    assert abs(eta - actual) <= 0.25 * actual, f"eta {eta:.2f} s, actual {actual:.2f} s"


def test_disk_full_during_a_job_fails_cleanly(settings, web_dist, corpus):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fake={"fail": "disk_full"}), base_url=BASE
    ) as client:
        job = wait(client, upload(client, corpus / "short-2s.wav").json()["id"], END)
    assert job["state"] == "failed"
    assert job["error"] == "The disk is full."
    assert not (settings.home / "outputs" / job["id"]).exists()
    assert not (settings.home / "work" / job["id"]).exists()


def test_library_size_and_clear_finished(client, corpus, settings):
    assert client.get("/api/library").json()["jobs"] == 0
    done = wait(client, upload(client, corpus / "short-2s.wav").json()["id"])
    rejected = upload(client, corpus / "empty.mp4").json()
    waiting = upload(client, corpus / "two-tracks.mkv").json()
    size = client.get("/api/library").json()
    upload_bytes = (corpus / "short-2s.wav").stat().st_size + (
        corpus / "two-tracks.mkv"
    ).stat().st_size
    assert size["jobs"] > upload_bytes
    assert size["folder"] == str(settings.home)
    cleared = client.post("/api/library/clear").json()
    assert cleared["removed"] == 2
    assert [j["id"] for j in client.get("/api/jobs").json()] == [waiting["id"]]
    assert cleared["jobs"] == (corpus / "two-tracks.mkv").stat().st_size
    assert done["id"] and rejected["id"]


def test_open_folder_opens_only_the_outputs_folder(client, settings, monkeypatch):
    opened = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: opened.append(args))
    assert client.post("/api/library/open").status_code == 204
    assert opened == [["xdg-open", str(settings.home / "outputs")]]


def test_retry_returns_to_an_unanswered_confirm(client, corpus):
    job = upload(client, corpus / "vp9-opus.webm", format="mov").json()
    assert job["state"] == "awaiting_confirm"
    client.post(f"/api/jobs/{job['id']}/cancel")
    assert client.post(f"/api/jobs/{job['id']}/retry").json()["state"] == "awaiting_confirm"


def test_retry_returns_to_an_unanswered_track_question(client, corpus):
    job = upload(client, corpus / "two-tracks.mkv").json()
    client.post(f"/api/jobs/{job['id']}/cancel")
    retried = client.post(f"/api/jobs/{job['id']}/retry").json()
    assert retried["state"] == "awaiting_track"
    assert [t["default"] for t in retried["tracks"]] == [True, False]


def test_closing_the_tab_mid_job_loses_nothing(live, long_mix):
    server = live(fake={"delay": 0.5})
    with httpx.Client(base_url=server.url) as client:
        job = upload(client, long_mix).json()
        first = events_until(server.url, lambda ev: True)  # connect, take the snapshot, leave
        assert first[0][1]["jobs"][0]["state"] in {"queued", *RUNNING}
        deadline = time.monotonic() + 60
        while client.get(f"/api/jobs/{job['id']}").json()["state"] != "done":
            assert time.monotonic() < deadline
            time.sleep(0.2)
        again = events_until(server.url, lambda ev: True)
    assert again[0][0] == "snapshot"
    assert again[0][1]["jobs"][0]["state"] == "done"
    assert again[0][1]["jobs"][0]["output_name"] == "five-minutes (no music).wav"


def test_data_folder_with_arabic_letters_and_spaces(tmp_path, corpus, web_dist):
    from sukoon.settings import Settings

    home = Settings(home=tmp_path / "مجلد البيانات" / "with spaces")
    home.ensure_dirs()
    with TestClient(fake_app(home, web_dist=web_dist), base_url=BASE) as client:
        job = wait(
            client,
            upload(client, corpus / "song-with-cover.mp3", name="أغنية مع غلاف.mp3").json()["id"],
            END,
        )
        assert job["state"] == "done"
        r = client.get(f"/api/jobs/{job['id']}/output")
    assert r.status_code == 200
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert job["output_name"] == "أغنية مع غلاف (no music).mp3"


# Measured at 144 MB (interpreter, numpy, soundfile, one chunk); the whole file is 1.4 GB.
PEAK_LIMIT = 400 * 1024**2


@pytest.mark.slow
@pytest.mark.skipif(not os.path.exists("/proc/self/status"), reason="reads peak memory from /proc")
def test_seventy_minutes_runs_in_constant_memory(tmp_path):
    """75 chunks for 4,200 s, and the worker's peak memory stays far below the whole file.

    The whole file as 32-bit float stereo is 1.4 GB; one chunk and its overlap are about 25 MB.
    """
    flac = fixture_script().make_silence_70min(tmp_path)
    scratch = tmp_path / "work" / "8a6f0c2e-2a8b-4f3e-9d61-2b1f4c9e7a10"
    scratch.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(flac),
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_f32le",
            str(scratch / "mixture.wav"),
        ],
        check=True,
    )
    worker = Worker(WorkerConfig(models_dir=tmp_path, fake={}))
    try:
        report = worker.separate(
            scratch / "mixture.wav",
            scratch / "voice.wav",
            scratch,
            lambda: False,
            lambda d, t: None,
            preset="fast",
            device="cpu",
        )
        with open(f"/proc/{worker.process.pid}/status") as f:
            peak_kb = next(int(line.split()[1]) for line in f if line.startswith("VmHWM"))
    finally:
        worker.stop()
    assert report.chunks == 75
    assert sf.info(str(scratch / "voice.wav")).frames == 4200 * 44100
    assert peak_kb * 1024 < PEAK_LIMIT
