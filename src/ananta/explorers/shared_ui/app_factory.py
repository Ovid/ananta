"""Generic FastAPI app factory for Ananta explorers.

Provides ``create_app()`` which builds a FastAPI instance with common
infrastructure: CORS middleware, a ``.well-known`` catch-all (suppresses
Chrome DevTools probing), optional static file serving, optional WebSocket
endpoint, and a lifespan hook that starts/stops the Ananta container pool.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from docker.errors import ImageNotFound
from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Hard cap on request body bytes. Without this, an unbounded POST is spooled
# to disk by Starlette before any application-level cap can react — disk-fill
# DoS reachable by any caller (I11). 256 MiB sits comfortably above the
# document-explorer's 200 MiB aggregate cap for a folder upload while still
# refusing any obviously-malicious request.
MAX_REQUEST_BODY_BYTES = 256 * 1024 * 1024


async def _send_413(send: Send) -> None:
    """Emit a 413 ASGI response."""
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": b"Request body too large"})


class _BodySizeLimitMiddleware:
    """Reject requests whose body exceeds *max_bytes* with a real 413.

    Two layers of defence:

    * Content-Length header check — fails fast before any body is consumed,
      and is the path a well-behaved (or merely lazy) HTTP client takes.
    * Streaming counter — meters ASGI ``receive()``; once cumulative inbound
      bytes exceed the cap the middleware emits a 413 directly and short-
      circuits the inner app.

    Implemented as a pure ASGI middleware (rather than ``BaseHTTPMiddleware``)
    because the BaseHTTP variant cannot synthesise a 413 from inside the
    streaming branch: it would only have a ``http.disconnect`` to return,
    which Starlette converts to ``ClientDisconnect`` and ultimately a 5xx.
    The pure-ASGI form also avoids assignment to ``request._receive``, which
    is a private attribute that CLAUDE.md forbids cross-module access to (I11).
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        max_bytes = self._max
        # Eager Content-Length check: refuse before any body is consumed.
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    # Malformed Content-Length — fall through to the
                    # streaming guard so a lying client is still capped.
                    break
                if declared > max_bytes:
                    await _send_413(send)
                    return
                break

        # Streaming guard. Meters ``receive()`` and switches to a 413 the
        # moment cumulative bytes exceed the cap. Once rejected, downstream
        # ``send`` calls are dropped so the inner app cannot smuggle out a
        # second response.
        seen = 0
        rejected = False

        async def metered_receive() -> Message:
            nonlocal seen, rejected
            msg = await receive()
            if rejected:
                # Once 413 is on the wire, any further reads from the inner
                # app see end-of-stream — this lets the handler unwind
                # cleanly instead of looping waiting for body chunks.
                return {"type": "http.disconnect"}
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > max_bytes:
                    rejected = True
                    await _send_413(send)
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg: Message) -> None:
            # Drop anything the inner app tries to emit after we've sent 413.
            if rejected:
                return
            await send(msg)

        try:
            await self._app(scope, metered_receive, guarded_send)
        except Exception:
            # Once 413 is on the wire, swallow exceptions from the inner
            # app — Starlette's ``request.body()`` typically raises
            # ``ClientDisconnect`` when our metered_receive returns a
            # synthetic disconnect, and there is nothing useful the inner
            # app can do after the response has already been sent.
            if not rejected:
                raise


def create_app(
    state: Any,
    title: str,
    *,
    static_dir: Path | None = None,
    images_dir: Path | None = None,
    ws_handler: Callable[..., Any] | None = None,
    extra_routers: list[APIRouter] | None = None,
) -> FastAPI:
    """Create a configured FastAPI application.

    Parameters
    ----------
    state:
        Application state object.  Must expose ``state.ananta`` with
        ``start()`` and ``stop()`` methods.
    title:
        The title for the FastAPI app (shown in OpenAPI docs).
    static_dir:
        Path to a built frontend directory.  When provided and the
        directory exists, it is mounted at ``/`` with ``html=True``
        (SPA catch-all).  Must be the *last* mount so it doesn't
        shadow other routes.
    images_dir:
        Path to a directory of images (logo, etc.).  Mounted at
        ``/static`` when provided and the directory exists.
    ws_handler:
        An async callable ``(WebSocket) -> None`` to mount at
        ``/api/ws``.  Omit to skip WebSocket support.
    extra_routers:
        Additional ``APIRouter`` instances to include in the app.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            state.ananta.start()
        except RuntimeError as e:
            print(f"\n[ananta] Error: {e}\n", file=sys.stderr)
            raise SystemExit(1) from e
        except ImageNotFound as e:
            explanation = getattr(e, "explanation", str(e))
            image = os.environ.get("ANANTA_SANDBOX_IMAGE", "ananta-sandbox")
            print(
                f"\n[ananta] Error: Docker image not found: {explanation}\n"
                "\n  Build it with:"
                f"\n    docker build -t {image} src/ananta/sandbox/\n",
                file=sys.stderr,
            )
            raise SystemExit(1) from e
        except Exception as e:
            print(f"\n[ananta] Error: {e}\n", file=sys.stderr)
            raise SystemExit(1) from e
        try:
            yield
        finally:
            state.ananta.stop()

    app = FastAPI(title=title, lifespan=lifespan)

    # Body-size middleware MUST be added before CORS so it runs first on
    # the inbound path; oversized requests are rejected before any
    # downstream middleware allocates resources.
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)

    # CORS — allow all origins during development.
    # allow_credentials intentionally omitted: no cookies/auth headers are
    # used, and combining credentials=True with wildcard origins causes
    # Starlette to reflect the request Origin, enabling any page to make
    # credentialed cross-origin requests.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Suppress Chrome DevTools probing (e.g. /.well-known/appspecific/...)
    @app.get("/.well-known/{path:path}", include_in_schema=False)
    def well_known(path: str) -> Response:
        return Response(status_code=204)

    # WebSocket endpoint
    if ws_handler is not None:
        _ws = ws_handler  # capture for the closure

        @app.websocket("/api/ws")
        async def ws_endpoint(ws: WebSocket) -> None:
            await _ws(ws)

    # Extra routers
    if extra_routers:
        for router in extra_routers:
            app.include_router(router)

    # Mount images directory at /static (before the SPA catch-all)
    if images_dir is not None and images_dir.exists():
        app.mount("/static", StaticFiles(directory=str(images_dir)))

    # Mount built frontend at / (catch-all — must be last)
    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return app
