import os
import shutil
import stat
import sys

import pytest
from fastapi.testclient import TestClient

from tests.conftest import BASE, fake_app
from tests.test_api import upload, wait


def test_settings_start_at_the_defaults_and_persist(settings, web_dist):
    with TestClient(fake_app(settings, web_dist=web_dist), base_url=BASE) as client:
        first = client.get("/api/settings").json()
        assert {k: first[k] for k in ("preset", "device", "audio_format", "video_format")} == {
            "preset": "best",
            "device": "auto",
            "audio_format": None,
            "video_format": None,
        }
        assert first["folder"] == str(settings.home)
        r = client.put("/api/settings", json={"preset": "fast", "audio_format": "flac"})
        assert r.json()["preset"] == "fast"
    with TestClient(fake_app(settings, web_dist=web_dist), base_url=BASE) as client:
        again = client.get("/api/settings").json()
    assert (again["preset"], again["audio_format"], again["device"]) == ("fast", "flac", "auto")


@pytest.mark.parametrize(
    "body",
    [
        {"preset": "ultra"},
        {"device": "gpu"},
        {"audio_format": "mp4"},
        {"video_format": "mp3"},
        {"theme": "dark"},
    ],
)
def test_bad_settings_are_refused(client, body):
    assert client.put("/api/settings", json=body).status_code in (400, 422)


def test_new_jobs_use_the_saved_choices(client, corpus):
    client.put(
        "/api/settings",
        json={"preset": "fast", "device": "cpu", "audio_format": "flac", "video_format": "mkv"},
    )
    audio = upload(client, corpus / "short-2s.wav").json()
    assert audio["options"]["preset"] == "fast"
    assert audio["options"]["device"] == "cpu"
    assert audio["options"]["format"] == "flac"
    video = upload(client, corpus / "offset-0.5s.mp4").json()
    assert video["options"]["format"] == "mkv"
    assert wait(client, video["id"])["output_name"] == "offset-0.5s (no music).mkv"


def test_device_setting_shows_in_the_status_line(client):
    client.put("/api/settings", json={"device": "cpu"})
    assert client.get("/api/health").json()["device"] == "CPU"


@pytest.fixture
def ffmpeg_without_mp3(tmp_path, monkeypatch):
    """A PATH whose ffmpeg is the real one, except that its encoder list lacks libmp3lame."""
    folder = tmp_path / "bin"
    folder.mkdir()
    real = shutil.which("ffmpeg")
    script = folder / "ffmpeg"
    script.write_text(f"""#!/bin/sh
case "$*" in
  *-encoders*) "{real}" "$@" | grep -v libmp3lame;;
  *) exec "{real}" "$@";;
esac
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    os.symlink(shutil.which("ffprobe"), folder / "ffprobe")
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.skipif(os.name == "nt", reason="the fake ffmpeg is a shell script")
def test_formats_without_an_encoder_are_disabled(settings, web_dist, corpus, ffmpeg_without_mp3):
    with TestClient(fake_app(settings, web_dist=web_dist), base_url=BASE) as client:
        assert client.get("/api/settings").json()["missing"] == {"mp3": "libmp3lame"}
        job = upload(client, corpus / "two-tracks.mkv").json()
        missing = {f["value"]: f["missing"] for f in job["formats"]}
        assert missing["mp3"] == "libmp3lame"
        assert missing["flac"] is None
        r = upload(client, corpus / "short-2s.wav", format="mp3")
        assert r.status_code == 400
        assert (
            r.json()["error"] == "MP3 needs the libmp3lame encoder, which this ffmpeg doesn't have."
        )
        r = client.post(f"/api/jobs/{job['id']}/choose", json={"format": "mp3"})
        assert r.status_code == 400


def test_missing_ffmpeg_shows_in_health_and_clears_when_it_returns(client, monkeypatch):
    path = os.environ["PATH"]
    monkeypatch.setenv("PATH", "")
    gone = client.get("/api/health").json()["ffmpeg"]
    command = {"win32": "winget install Gyan.FFmpeg", "darwin": "brew install ffmpeg"}
    assert gone == {"ok": False, "install": command.get(sys.platform, "sudo apt install ffmpeg")}
    monkeypatch.setenv("PATH", path)
    assert client.get("/api/health").json()["ffmpeg"]["ok"] is True
