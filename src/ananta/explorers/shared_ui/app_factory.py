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


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _origin_matches_host(origin: str, host: str) -> bool:
    """Return True iff *origin* (``scheme://host[:port]``) and *host*
    (``host[:port]``) refer to the same host:port pair.

    Origin is only compared by host:port, not scheme — a same-host upgrade
    (e.g., http→https on the same loopback port) shouldn't trip the guard
    even though we have no realistic deployment that does that today.
    """
    if "://" not in origin:
        return False
    origin_host = origin.split("://", 1)[1]
    return origin_host == host


class _SameOriginGuardMiddleware:
    """Reject mutating HTTP requests and WebSocket handshakes whose Origin
    does not match the Host.

    Threat model (C2): the explorer is launched as a localhost daemon and
    has no authentication. Without this guard, any web page the user visits
    while the explorer is running can submit a multipart POST to
    ``http://localhost:<port>/api/documents/upload`` — and the same threat
    applies to ``ws://localhost:<port>/api/ws`` (drain LLM credits via
    expensive iterative queries, exfiltrate streamed answers/traces, trigger
    sandbox container starts the operator pays for; I1).

    Browsers attach an ``Origin`` header to every cross-origin HTTP request
    and to every WebSocket handshake, so we can refuse a request whose
    Origin does not match Host. Same-origin requests from the explorer's
    own served HTML pass through; direct API callers (curl, Python scripts)
    usually omit Origin and are also allowed — that traffic is not the
    threat.

    Read-only HTTP methods (GET/HEAD) are exempt — the same-origin policy
    already prevents reading their bodies cross-origin in a browser. WS
    connections, by contrast, are always treated as mutating: there is no
    read-only WS in this app, and an open socket is itself a credit drain.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type == "http":
            if scope["method"] not in _MUTATING_METHODS:
                await self._app(scope, receive, send)
                return
        elif scope_type != "websocket":
            await self._app(scope, receive, send)
            return

        origin = ""
        host = ""
        for name, value in scope["headers"]:
            if name == b"origin":
                origin = value.decode("latin-1")
            elif name == b"host":
                host = value.decode("latin-1")
        if origin and not _origin_matches_host(origin, host):
            if scope_type == "http":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Cross-origin request refused"})
            else:
                # WebSocket close before accept. 1008 = policy violation.
                await send({"type": "websocket.close", "code": 1008})
            return
        await self._app(scope, receive, send)


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

    # Middleware ordering note: Starlette's add_middleware inserts at
    # index 0 of user_middleware, so the LAST add_middleware call wraps
    # the OUTERMOST layer at runtime. The desired runtime order
    # (outermost → innermost on the inbound path) is:
    #
    #   _BodySizeLimitMiddleware  ← outermost: rejects oversized bodies
    #                                before any downstream middleware
    #                                allocates resources
    #   _SameOriginGuardMiddleware ← drive-by upload defence (C2)
    #   CORSMiddleware             ← innermost
    #
    # To achieve that, add them in REVERSE order: CORS first (innermost),
    # then SameOrigin, then BodySizeLimit last (outermost).

    # CORS — wildcard origins. The actual cross-origin threat (drive-by
    # uploads from arbitrary visited pages) is handled by the same-origin
    # guard, which compares Origin to Host per request. We don't restrict
    # CORS by hostname here because operators may bind the explorer to
    # an internal address (e.g., a LAN host) where the legitimate Origin
    # is whatever they've deployed under, not just loopback.
    # allow_credentials is intentionally omitted: no cookies/auth headers
    # are used, and combining credentials=True with wildcard origins
    # causes Starlette to reflect the request Origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Same-origin guard for mutating methods. Defends against drive-by
    # uploads from arbitrary visited pages — see _SameOriginGuardMiddleware
    # for the full threat model (C2).
    app.add_middleware(_SameOriginGuardMiddleware)

    # Body-size middleware is added LAST so it sits OUTERMOST at runtime;
    # oversized requests are rejected before any downstream middleware
    # allocates resources or reads the body. Future maintainers adding
    # a body-reading middleware (request logging, metrics, audit) MUST
    # add it before this line — anything added after will land outside
    # the cap and process unbounded bodies.
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)

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
