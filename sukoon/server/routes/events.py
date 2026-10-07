"""The live feed the interface listens to: every job and model change, as it happens."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from sukoon.jobs.store import Job
from sukoon.separation.models import PRESETS
from sukoon.server.services import Services

KEEPALIVE_S = 15.0


def sse(event: str, data: object) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


async def event_stream(services: Services) -> AsyncIterator[bytes]:
    """A snapshot of every job on connect, then each change as it happens."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_job(event: str, job: Job) -> None:
        payload = (
            sse("job", services.view(job)) if event == "job" else sse("deleted", {"id": job["id"]})
        )
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    def on_model(state: dict[str, object]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, sse("model", state))

    unsubscribe = services.store.subscribe(on_job)
    services.model_listeners.append(on_model)
    try:
        yield sse(
            "snapshot",
            {
                "jobs": [services.view(j) for j in services.store.list()],
                "models": [services.downloads.state(p) for p in PRESETS],
            },
        )
        while True:
            try:
                yield await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except TimeoutError:
                yield b": keep-alive\n\n"
    finally:
        unsubscribe()
        services.model_listeners.remove(on_model)


def router(services: Services) -> APIRouter:
    r = APIRouter()

    @r.get("/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(
            event_stream(services),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache"},
        )

    return r
