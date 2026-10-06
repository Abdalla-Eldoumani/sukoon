from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sukoon import __version__, tools
from sukoon.api import Services, build_router
from sukoon.device import detect_cached
from sukoon.download import Downloads
from sukoon.models import Preset
from sukoon.runner import Runner
from sukoon.settings import Settings
from sukoon.store import Store
from sukoon.worker import Worker, WorkerConfig

WEB_DIST = Path(__file__).parent / "web_dist"

SECURITY_HEADERS = [
    (
        b"content-security-policy",
        b"default-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; "
        b"style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    ),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class LocalOnlyMiddleware:
    """Refuses foreign Host headers (DNS rebinding) and foreign Origins on writes (CSRF)."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        self.app = app
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{h}" for h in self.hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + SECURITY_HEADERS
            await send(message)

        if headers.get("host") not in self.hosts:
            await PlainTextResponse("Unknown host.", 400)(scope, receive, send_with_headers)
            return
        origin = headers.get("origin")
        # A browser always sends Origin on cross-site writes; scripts and curl send none.
        if scope["method"] in UNSAFE_METHODS and origin is not None and origin not in self.origins:
            await PlainTextResponse("Cross-origin request refused.", 403)(
                scope, receive, send_with_headers
            )
            return
        await self.app(scope, receive, send_with_headers)


def create_app(
    settings: Settings,
    port: int,
    web_dist: Path = WEB_DIST,
    worker_config: WorkerConfig | None = None,
    model_ready: Callable[[Preset], bool] | None = None,
) -> ASGIApp:
    """The whole server. Tests pass a fake engine config and their own idea of model readiness."""
    settings.ensure_dirs()
    config = worker_config or WorkerConfig(models_dir=settings.area("models"))
    store = Store(settings.db_path)
    downloads = Downloads(config.models_dir, lambda s: None, lambda: None, config.model_files)
    ready = model_ready or (lambda preset: bool(downloads.state(preset)["ready"]))
    runner = Runner(settings, store, Worker(config), ready)
    services = Services(settings, store, runner, downloads)
    services.available_encoders()  # Once at startup, so the format menus know what works.
    downloads.on_change = services.model_changed
    downloads.on_ready = runner.models_changed

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        runner.start()
        try:
            yield
        finally:
            runner.stop()
            store.close()

    app = FastAPI(
        title="sukoon",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.services = services
    app.include_router(build_router(services))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        """Checked on every call, so the setup screen's Check again sees a fresh install."""
        cpu = store.settings()["device"] == "cpu"
        return {
            "status": "ok",
            "app": "sukoon",
            "version": __version__,
            "ffmpeg": {
                "ok": tools.ffmpeg_path() is not None and tools.ffprobe_path() is not None,
                "install": tools.ffmpeg_install_command(),
            },
            "device": detect_cached("cpu" if cpu else "auto").label,
        }

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        root = web_dist.resolve()
        index = root / "index.html"
        if path.startswith("api/"):
            return PlainTextResponse("Not found.", 404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index, headers={"cache-control": "no-cache"})
        return PlainTextResponse("The interface has not been built. Run scripts/build_web.py.", 503)

    return LocalOnlyMiddleware(app, port)
