import pytest
from fastapi.testclient import TestClient

from sukoon.app import create_app
from sukoon.settings import Settings

PORT = 8417
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def settings(tmp_path):
    s = Settings(home=tmp_path / "data")
    s.ensure_dirs()
    return s


@pytest.fixture
def web_dist(tmp_path):
    d = tmp_path / "web_dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>sukoon</title>")
    (d / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside")
    return d


@pytest.fixture
def client(settings, web_dist):
    with TestClient(create_app(settings, PORT, web_dist=web_dist), base_url=BASE) as c:
        yield c
