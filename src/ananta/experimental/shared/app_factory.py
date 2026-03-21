"""Generic FastAPI app factory for Ananta experimental tools.

Provides ``create_app()`` which builds a FastAPI instance with common
infrastructure: CORS middleware, a ``.well-known`` catch-all (suppresses
Chrome DevTools probing), optional static file serving, optional WebSocket
endpoint, and a lifespan hook that starts/stops the Ananta container pool.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response


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
        try:
            yield
        finally:
            state.ananta.stop()

    app = FastAPI(title=title, lifespan=lifespan)

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
