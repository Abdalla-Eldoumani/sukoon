import importlib.util
import socket
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest
import uvicorn
from fastapi.testclient import TestClient

from sukoon.separation.worker import WorkerConfig
from sukoon.server.app import create_app
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


def fake_app(settings, port=PORT, web_dist=None, fake=None, **kwargs):
    """The real app with the fake engine in its worker; models count as ready unless told."""
    kwargs.setdefault("model_ready", lambda preset: True)
    config = WorkerConfig(
        models_dir=settings.area("models"), fake=fake or {}, **kwargs.pop("worker", {})
    )
    extra = {"web_dist": web_dist} if web_dist else {}
    return create_app(settings, port, worker_config=config, **extra, **kwargs)


@pytest.fixture
def client(settings, web_dist):
    with TestClient(fake_app(settings, web_dist=web_dist), base_url=BASE) as c:
        yield c


class LiveServer:
    """The app on a real loopback port, for streams the test client cannot hold open."""

    def __init__(self, app_factory):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(app_factory(self.port), log_level="warning"))
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=30)


@pytest.fixture
def live(settings):
    servers = []

    def start(**kwargs):
        server = LiveServer(lambda port: fake_app(settings, port=port, **kwargs))
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.stop()


ROOT = Path(__file__).resolve().parent.parent


def fixture_script() -> ModuleType:
    """scripts/make_fixtures.py, which is not part of the package."""
    spec = importlib.util.spec_from_file_location(
        "make_fixtures", ROOT / "scripts" / "make_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def corpus():
    """The generated fixture folder, built once if it is missing."""
    out = ROOT / "tests" / "fixtures" / "generated"
    if not (out / "truncated.mp4").exists():
        fixture_script().build(out)
    return out
