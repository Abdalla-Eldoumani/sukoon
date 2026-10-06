import json
import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sukoon import doctor
from sukoon.doctor import age_in_days, node_major
from sukoon.errors import JobError
from sukoon.links import (
    AGE,
    CRASHED,
    DRM,
    ELSEWHERE,
    LIVE,
    NETWORK,
    PLAYLIST,
    PRIVATE,
    REGION,
    STALLED,
    LinkRefused,
    explain,
    fetch,
    refusal,
    site,
)
from sukoon.probe import PLAYLIST as PLAYLIST_FILE
from tests.conftest import BASE, fake_app
from tests.test_api import wait

GENERATED = Path(__file__).resolve().parent / "fixtures" / "generated"
SIX_HOURS = 6 * 3600
EIGHT_GB = 8 * 1024**3


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube.com"),
        ("https://youtube.com/watch?v=jNQXAC9IVRw&list=PL1", "youtube.com"),
        ("https://m.youtube.com/shorts/abc", "youtube.com"),
        ("https://youtu.be/jNQXAC9IVRw", "youtu.be"),
        ("https://x.com/user/status/1", "x.com"),
        ("https://twitter.com/user/status/1", "twitter.com"),
        ("https://www.instagram.com/reel/abc/", "instagram.com"),
        ("https://www.tiktok.com/@u/video/1", "tiktok.com"),
        ("https://www.facebook.com/reel/1", "facebook.com"),
        ("https://fb.watch/abc/", "fb.watch"),
        ("https://old.reddit.com/r/a/comments/b/", "reddit.com"),
        ("https://v.redd.it/abc", "v.redd.it"),
        ("https://vimeo.com/68375962", "vimeo.com"),
        ("https://soundcloud.com/a/b", "soundcloud.com"),
        ("  https://YOUTUBE.com/watch?v=x  ", "youtube.com"),
    ],
)
def test_accepts_the_listed_sites(url, expected):
    assert site(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.example/watch?v=x",
        "https://evil.example/youtube.com",
        "evil.example/youtube.com",
        "https://notyoutube.com/watch?v=x",
        "https://youtube.com:8080/watch?v=x",
        "https://youtube.com:443/watch?v=x",
        "https://youtube.com@evil.example/watch?v=x",
        "https://user:pass@youtube.com/watch?v=x",
        "javascript:alert(1)",
        "file:///C:/Windows/win.ini",
        "http://youtube.com/watch?v=x",
        "https://уoutube.com/watch?v=x",  # a Cyrillic letter in place of the y
        "https://youtube.com./watch?v=x",
        "https://142.250.72.14/watch?v=x",
        "https://[::1]/watch?v=x",
        "https://xn--outube-4nf.com/watch?v=x",
        "",
        "youtube",
    ],
)
def test_refuses_anything_else_with_a_sentence_naming_the_sites(url):
    with pytest.raises(LinkRefused) as refused:
        site(url)
    assert "YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and SoundCloud" in str(
        refused.value
    )


def video(**fields):
    part = {"format_id": "1", "protocol": "https", "filesize": 10_000_000}
    return {"duration": 60, "requested_formats": [part, dict(part)], **fields}


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        ({"_type": "playlist"}, PLAYLIST),
        (video(is_live=True), LIVE),
        (video(live_status="is_upcoming"), LIVE),
        (video(live_status="post_live"), LIVE),
        (video(requested_formats=[{"format_id": "1", "has_drm": True}]), DRM),
        (
            video(duration=6 * 3600 + 1),
            "This video is longer than 6 hours, which is sukoon's limit.",
        ),
        (
            video(requested_formats=[{"format_id": "1", "filesize": 9 * 1024**3}]),
            "This video is bigger than 8 GB, which is sukoon's limit.",
        ),
        # No size given: the bitrate (kilobits per second) over the duration stands in.
        (
            video(duration=5 * 3600, requested_formats=[{"format_id": "1", "tbr": 5000}]),
            "This video is bigger than 8 GB, which is sukoon's limit.",
        ),
        (
            video(requested_formats=[{"format_id": "1", "protocol": "rtmp"}]),
            "This video is only offered as a kind of stream sukoon doesn't fetch.",
        ),
    ],
)
def test_metadata_rules_a_link_out_before_downloading(info, reason):
    assert refusal(info, SIX_HOURS, EIGHT_GB) == reason


def test_an_ordinary_video_passes_the_metadata_checks():
    assert refusal(video(), SIX_HOURS, EIGHT_GB) is None


@pytest.mark.parametrize(
    ("message", "family", "expected"),
    [
        (
            "ERROR: [youtube] abc: Private video. Sign in if you've been granted access",
            "youtube",
            PRIVATE,
        ),
        (
            "ERROR: [youtube] abc: Video unavailable. This video has been removed",
            "youtube",
            PRIVATE,
        ),
        (
            "ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate "
            "for some users.",
            "youtube",
            AGE,
        ),
        (
            "ERROR: [youtube] abc: The uploader has not made this video available in your country",
            "youtube",
            REGION,
        ),
        (
            "ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies, "
            "--cookies-from-browser, --username and --password",
            "vimeo",
            "Vimeo only shares this video with signed-in people, and sukoon never signs in. "
            "Save it another way and drop the file here.",
        ),
        ("ERROR: [youtube] abc: This live event will begin in 3 hours.", "youtube", LIVE),
        (
            "ERROR: No suitable extractor (youtube) found for URL https://www.youtube.com/x",
            "reddit",
            ELSEWHERE,
        ),
        (
            "ERROR: [twitter] 1: Unable to download webpage: <urlopen error [Errno 11001] "
            "getaddrinfo failed>",
            "twitter",
            NETWORK,
        ),
        (
            "ERROR: [TikTok] 1: Unexpected response from webpage request; please report this "
            "issue on https://github.com/yt-dlp/yt-dlp/issues",
            "tiktok",
            "yt-dlp couldn't read this TikTok page. Its reader may be out of date, or TikTok "
            "turned the request away. To update it, run: uv lock --upgrade-package yt-dlp "
            "--upgrade-package yt-dlp-ejs && uv sync",
        ),
        (
            "ERROR: [youtube] abc: something new happened",
            "youtube",
            "Couldn't fetch this video. yt-dlp said: something new happened",
        ),
    ],
)
def test_each_yt_dlp_failure_becomes_a_sentence(message, family, expected):
    assert explain(message, family) == expected


def test_a_geo_block_is_a_region_sentence_whatever_its_wording():
    assert explain("ERROR: [youtube] abc: blocked", "youtube", geo=True) == REGION


def fake_fetch(url, folder, outbox, max_seconds, max_bytes):
    """The downloader seam: acts out what the link's last word asks for, with fixture files."""
    folder = Path(folder)
    what = url.rsplit("=", 1)[-1]
    if what == "stall":
        time.sleep(120)
    if what == "crash":
        os._exit(3)
    if what == "private":
        outbox.put(("error", PRIVATE))
        return
    outbox.put(("title", f"Talk: part 1 / {what}"))
    if what == "playlist":
        (folder / "part0.mp4").write_text("#EXTM3U\nfile:///C:/Windows/win.ini\n")
    elif what == "split":
        source = str(GENERATED / "offset-0.5s.mp4")
        for args in (["-an", str(folder / "part0.mp4")], ["-vn", str(folder / "part1.m4a")]):
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", source, "-c", "copy", *args], check=True
            )
    else:
        name = {"audio": "speech-over-music-30s.wav"}.get(what, "offset-0.5s.mp4")
        shutil.copy(GENERATED / name, folder / f"part0{Path(name).suffix}")
    outbox.put(("progress", (500, 1000)))
    outbox.put(("progress", (1000, 1000)))
    outbox.put(("done", sorted(str(p) for p in folder.glob("part*"))))


def link(client, what, **body):
    r = client.post("/api/links", json={"url": f"https://www.youtube.com/watch?v={what}", **body})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def links_client(settings, web_dist, corpus):
    app = fake_app(settings, web_dist=web_dist, fetch_options={"target": fake_fetch})
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_a_link_is_fetched_checked_and_cleaned_into_mp4(links_client, settings):
    job = link(links_client, "video")
    assert job["state"] == "fetching"
    assert job["link"]["site"] == "youtube.com"
    job = wait(links_client, job["id"])
    assert job["state"] == "done", job
    assert job["name"] == "Talk: part 1 / video.mp4"
    assert job["link"]["done"] == job["link"]["total"] == 1000
    assert job["output_name"] == "Talk- part 1 - video (no music).mp4"
    out = settings.job_path("outputs", job["id"])
    assert (out / "output.mp4").is_file()
    assert (out / "peaks.json").is_file()


def test_video_and_audio_parts_are_joined_into_one_source(links_client, settings):
    job = wait(links_client, link(links_client, "split")["id"])
    assert job["state"] == "done", job
    assert job["kind"] == "video"
    assert sorted(p.name for p in settings.job_path("uploads", job["id"]).iterdir()) == [
        "source.mp4"
    ]


def test_an_audio_only_link_defaults_to_m4a(links_client):
    job = wait(links_client, link(links_client, "audio")["id"])
    assert job["state"] == "done", job
    assert job["output_name"].endswith(".m4a")


def test_download_only_copies_the_file_without_separating_it(links_client, settings, tmp_path):
    job = wait(links_client, link(links_client, "video", keep_music=True)["id"])
    assert job["state"] == "done", job
    assert job["output_name"] == "Talk- part 1 - video.mp4"
    out = settings.job_path("outputs", job["id"])
    assert sorted(p.name for p in out.iterdir()) == ["output.mp4"]
    streams = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_streams", str(out / "output.mp4")],
            capture_output=True,
            check=True,
        ).stdout
    )["streams"]
    source = GENERATED / "offset-0.5s.mp4"
    original = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_streams", str(source)],
            capture_output=True,
            check=True,
        ).stdout
    )["streams"]
    assert [s["codec_name"] for s in streams] == [s["codec_name"] for s in original]


def test_the_remove_music_switch_can_change_before_the_job_runs(links_client):
    job = link(links_client, "stall")
    r = links_client.post(f"/api/jobs/{job['id']}/choose", json={"keep_music": True})
    assert r.json()["options"]["keep_music"] is True
    links_client.post(f"/api/jobs/{job['id']}/cancel")


def test_a_failed_fetch_says_why_and_can_be_retried(links_client, settings):
    job = wait(links_client, link(links_client, "private")["id"])
    assert job["state"] == "failed"
    assert job["error"] == PRIVATE
    assert job["retryable"]
    r = links_client.post(f"/api/jobs/{job['id']}/retry")
    assert r.json()["state"] == "fetching"
    assert wait(links_client, job["id"])["error"] == PRIVATE


def test_a_downloaded_playlist_is_refused_like_an_upload(links_client, settings):
    job = wait(links_client, link(links_client, "playlist")["id"])
    assert job["state"] == "failed"
    assert job["error"] == PLAYLIST_FILE
    assert not settings.job_path("uploads", job["id"]).exists()


def test_cancel_stops_the_download_at_once(links_client, settings):
    job = link(links_client, "stall")
    time.sleep(1)
    links_client.post(f"/api/jobs/{job['id']}/cancel")
    job = wait(links_client, job["id"], states={"canceled"}, timeout=10)
    deadline = time.monotonic() + 10
    while settings.job_path("uploads", job["id"]).exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not settings.job_path("uploads", job["id"]).exists()


def test_a_refused_link_never_becomes_a_job(links_client):
    r = links_client.post("/api/links", json={"url": "https://youtube.com.evil.example/watch?v=x"})
    assert r.status_code == 400
    assert "YouTube, X, Instagram" in r.json()["error"]
    assert links_client.get("/api/jobs").json() == []


def test_a_silent_download_fails_the_job(tmp_path):
    with pytest.raises(JobError, match=STALLED):
        fetch(
            "https://www.youtube.com/watch?v=stall",
            tmp_path,
            lambda done, total: None,
            lambda: False,
            SIX_HOURS,
            EIGHT_GB,
            target=fake_fetch,
            stall_s=2,
        )


def test_a_crashed_download_fails_the_job(tmp_path):
    with pytest.raises(JobError, match=CRASHED):
        fetch(
            "https://www.youtube.com/watch?v=crash",
            tmp_path,
            lambda done, total: None,
            lambda: False,
            SIX_HOURS,
            EIGHT_GB,
            target=fake_fetch,
        )


def test_a_restart_during_a_fetch_leaves_it_interrupted_with_retry(settings, web_dist, corpus):
    with TestClient(
        fake_app(settings, web_dist=web_dist, fetch_options={"target": fake_fetch}),
        base_url=BASE,
    ) as c:
        job = link(c, "stall")
    with TestClient(
        fake_app(settings, web_dist=web_dist, fetch_options={"target": fake_fetch}),
        base_url=BASE,
    ) as c:
        again = c.get(f"/api/jobs/{job['id']}").json()
        assert again["state"] == "interrupted"
        assert again["retryable"]


def test_doctor_counts_yt_dlp_age_from_its_version():
    assert age_in_days("2026.8.19", date(2026, 10, 18)) == 60
    assert age_in_days("2026.08.19", date(2026, 8, 19)) == 0
    assert age_in_days("2026.8.19.1", date(2026, 8, 20)) == 1
    assert age_in_days("nightly", date(2026, 8, 20)) is None


def test_doctor_reads_the_node_major_version():
    assert node_major("v24.7.0") == 24
    assert node_major("v20.11.1\n") == 20
    assert node_major("") is None


def test_doctor_notes_an_old_yt_dlp_with_the_update_command(settings):
    lines = []
    doctor.run(settings, out=lines.append, today=date(2027, 1, 1))
    text = "\n".join(lines)
    assert "--   yt-dlp     2026.8.19, 135 days old" in text
    assert "uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync" in text
