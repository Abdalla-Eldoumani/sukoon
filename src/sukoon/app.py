from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sukoon import __version__
from sukoon.device import detect_cached
from sukoon.settings import Settings

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


def create_app(settings: Settings, port: int, web_dist: Path = WEB_DIST) -> ASGIApp:
    app = FastAPI(
        title="sukoon", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": "sukoon",
            "version": __version__,
            "device": detect_cached().label,
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
