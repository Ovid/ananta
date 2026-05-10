"""Tests for the shared FastAPI app factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from ananta.explorers.shared_ui.app_factory import create_app


def _make_state() -> MagicMock:
    """Create a minimal mock state with an ananta attribute."""
    state = MagicMock()
    state.ananta = MagicMock()
    state.ananta.start = MagicMock()
    state.ananta.stop = MagicMock()
    return state


# -- Body-size limiting middleware (I11) --


def _add_echo_route(app: FastAPI) -> None:
    """Add a tiny POST endpoint so we can drive the middleware."""
    from starlette.requests import Request
    from starlette.routing import Route

    async def echo(request: Request) -> Any:
        from starlette.responses import JSONResponse

        body = await request.body()
        return JSONResponse({"len": len(body)})

    app.router.routes.append(Route("/echo", echo, methods=["POST"]))


def test_oversized_content_length_rejected_with_413() -> None:
    """A Content-Length header above the cap is rejected with 413.

    Reproduces I11: a malicious POST without our application-level cap
    would spool a multi-gigabyte body to disk before the handler ran,
    enabling disk-fill DoS. The middleware fails fast before any spooling.
    """
    from ananta.explorers.shared_ui.app_factory import MAX_REQUEST_BODY_BYTES

    state = _make_state()
    app = create_app(state, title="Test App")
    _add_echo_route(app)
    client = TestClient(app)
    # We claim more than the cap via Content-Length; the body itself isn't
    # actually that big — that's the point: the handler never runs.
    headers = {"Content-Length": str(MAX_REQUEST_BODY_BYTES + 1)}
    resp = client.post("/echo", content=b"x", headers=headers)
    assert resp.status_code == 413


@pytest.mark.anyio
async def test_streamed_body_without_content_length_returns_413() -> None:
    """A chunked / no-Content-Length body exceeding the cap returns 413.

    Reproduces the streaming-path gap (C1): httpx's TestClient always sets
    Content-Length, so the eager header check at the top of the middleware
    catches it before the streaming counter ever runs. To exercise the
    streaming branch we drive the app via ASGITransport with an async-
    generator body, which httpx sends as chunked transfer-encoding (no
    Content-Length). The middleware must respond with a real 413, not a
    503/500-via-ClientDisconnect or a partial response.

    The test wires _BodySizeLimitMiddleware directly with a small cap so it
    runs in milliseconds rather than allocating hundreds of MiB.
    """
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from ananta.explorers.shared_ui.app_factory import _BodySizeLimitMiddleware

    cap = 1024  # 1 KiB cap keeps the test fast.

    async def echo(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"len": len(body)})

    app = Starlette(routes=[Route("/echo", echo, methods=["POST"])])
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=cap)

    async def chunked_body() -> Any:
        # Two 700-byte chunks → 1400 bytes total > 1024 cap. httpx encodes
        # this with Transfer-Encoding: chunked and no Content-Length header.
        for _ in range(2):
            yield b"\x00" * 700

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/echo", content=chunked_body())
        assert resp.status_code == 413


def test_normal_request_unaffected_by_size_middleware() -> None:
    """A small request still succeeds end-to-end."""
    state = _make_state()
    app = create_app(state, title="Test App")
    _add_echo_route(app)
    client = TestClient(app)
    resp = client.post("/echo", content=b"hello")
    assert resp.status_code == 200
    assert resp.json() == {"len": 5}


# -- Same-origin guard middleware (C2) --


def test_post_with_cross_origin_rejected_with_403() -> None:
    """POST from a foreign Origin header is rejected.

    The drive-by upload threat (C2): the explorer's CORSMiddleware originally
    set ``allow_origins=["*"]`` and the upload endpoint had no auth, so any
    web page the user visited could POST a 256 MiB body of attacker-chosen
    documents into the local RLM corpus. The Origin guard refuses any
    mutating request whose ``Origin`` header does not match its ``Host``.
    """
    state = _make_state()
    app = create_app(state, title="Test App")
    _add_echo_route(app)
    client = TestClient(app)
    resp = client.post(
        "/echo",
        content=b"x",
        headers={"origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403


def test_post_with_matching_origin_accepted() -> None:
    """POST with Origin equal to Host is accepted (same-origin from a browser)."""
    state = _make_state()
    app = create_app(state, title="Test App")
    _add_echo_route(app)
    client = TestClient(app)
    # TestClient defaults Host to ``testserver``; mirror it in Origin so the
    # origin-guard middleware sees a same-origin request.
    resp = client.post(
        "/echo",
        content=b"x",
        headers={"origin": "http://testserver"},
    )
    assert resp.status_code == 200


def test_post_without_origin_accepted() -> None:
    """POST with no Origin header (curl, scripts) is accepted.

    Browsers always set ``Origin`` on cross-origin POSTs — that's the threat
    surface we cover. Direct API callers from a trusted shell (curl, the
    user's own scripts) typically omit it; we must not break them.
    """
    state = _make_state()
    app = create_app(state, title="Test App")
    _add_echo_route(app)
    client = TestClient(app)
    resp = client.post("/echo", content=b"x")
    assert resp.status_code == 200


def test_get_with_cross_origin_unaffected_by_origin_guard() -> None:
    """GET requests are not rejected by the origin guard."""
    state = _make_state()
    app = create_app(state, title="Test App")
    client = TestClient(app)
    resp = client.get(
        "/.well-known/anything",
        headers={"origin": "http://evil.example.com"},
    )
    # 204 from the well-known catch-all; the point is it's NOT 403.
    assert resp.status_code == 204


# -- Basic app creation --


def test_create_app_returns_fastapi_instance() -> None:
    """create_app returns a FastAPI instance with the given title."""
    state = _make_state()
    app = create_app(state, title="Test App")
    assert isinstance(app, FastAPI)
    assert app.title == "Test App"


def test_create_app_has_cors_middleware() -> None:
    """create_app adds CORSMiddleware to the app."""
    state = _make_state()
    app = create_app(state, title="Test App")
    # Starlette stores middleware in app.user_middleware
    middleware_classes = [m.cls for m in app.user_middleware]
    assert CORSMiddleware in middleware_classes


def test_body_size_middleware_is_outermost() -> None:
    """_BodySizeLimitMiddleware sits OUTERMOST so oversized bodies are rejected
    before any downstream middleware allocates resources or reads the body.

    Starlette's add_middleware inserts at index 0 of user_middleware, so the
    LAST add_middleware call wraps the OUTERMOST runtime layer. That means
    user_middleware[0] is the outermost, user_middleware[-1] is the innermost.
    A regression here (e.g., reordering the calls in app_factory.py) would
    silently route unbounded bodies through other middleware before the cap
    can fire.
    """
    from ananta.explorers.shared_ui.app_factory import (
        _BodySizeLimitMiddleware,
        _SameOriginGuardMiddleware,
    )

    state = _make_state()
    app = create_app(state, title="Test App")
    middleware_classes = [m.cls for m in app.user_middleware]
    assert middleware_classes[0] is _BodySizeLimitMiddleware, (
        f"BodySizeLimit must be outermost; got order {middleware_classes}"
    )
    body_idx = middleware_classes.index(_BodySizeLimitMiddleware)
    same_origin_idx = middleware_classes.index(_SameOriginGuardMiddleware)
    cors_idx = middleware_classes.index(CORSMiddleware)
    assert body_idx < same_origin_idx < cors_idx, (
        "Expected outermost→innermost ordering "
        "BodySizeLimit → SameOriginGuard → CORS; got "
        f"{middleware_classes}"
    )


# -- .well-known route --


def test_well_known_returns_204() -> None:
    """The .well-known catch-all route returns 204 No Content."""
    state = _make_state()
    app = create_app(state, title="Test App")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/.well-known/appspecific/com.chrome.devtools")
    assert response.status_code == 204


def test_well_known_not_in_openapi_schema() -> None:
    """The .well-known route is excluded from the OpenAPI schema."""
    state = _make_state()
    app = create_app(state, title="Test App")
    schema = app.openapi()
    # No .well-known paths should appear in the schema
    well_known_paths = [p for p in schema.get("paths", {}) if ".well-known" in p]
    assert well_known_paths == []


# -- WebSocket mounting --


def test_websocket_endpoint_mounted_when_handler_provided() -> None:
    """When ws_handler is given, a WebSocket endpoint is mounted at /api/ws."""
    state = _make_state()

    async def dummy_ws_handler(ws: object) -> None:
        pass

    app = create_app(state, title="Test App", ws_handler=dummy_ws_handler)
    # Find a route matching /api/ws
    ws_routes = [r for r in app.routes if getattr(r, "path", None) == "/api/ws"]
    assert len(ws_routes) == 1


def test_no_websocket_endpoint_without_handler() -> None:
    """When ws_handler is None, no WebSocket endpoint is mounted."""
    state = _make_state()
    app = create_app(state, title="Test App")
    ws_routes = [r for r in app.routes if getattr(r, "path", None) == "/api/ws"]
    assert len(ws_routes) == 0


# -- Static file mounting --


def test_static_dir_mounted_at_root(tmp_path: Path) -> None:
    """When static_dir is provided and exists, it is mounted at / (catch-all for SPA)."""
    state = _make_state()
    # Create a minimal static file
    index = tmp_path / "index.html"
    index.write_text("<h1>Hello</h1>")

    app = create_app(state, title="Test App", static_dir=tmp_path)
    # Find a mount at "/"
    root_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "" and isinstance(r.app, StaticFiles)
    ]
    assert len(root_mounts) == 1


def test_static_dir_not_mounted_when_none() -> None:
    """When static_dir is None, no root static mount is added."""
    state = _make_state()
    app = create_app(state, title="Test App")
    root_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "" and isinstance(r.app, StaticFiles)
    ]
    assert len(root_mounts) == 0


def test_static_dir_not_mounted_when_missing() -> None:
    """When static_dir does not exist on disk, no root static mount is added."""
    state = _make_state()
    app = create_app(state, title="Test App", static_dir=Path("/nonexistent/path"))
    root_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "" and isinstance(r.app, StaticFiles)
    ]
    assert len(root_mounts) == 0


def test_images_dir_mounted_at_static(tmp_path: Path) -> None:
    """When images_dir is provided and exists, it is mounted at /static."""
    state = _make_state()
    # Create a minimal image placeholder
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")

    app = create_app(state, title="Test App", images_dir=tmp_path)
    static_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "/static" and isinstance(r.app, StaticFiles)
    ]
    assert len(static_mounts) == 1


def test_images_dir_not_mounted_when_none() -> None:
    """When images_dir is None, no /static mount is added."""
    state = _make_state()
    app = create_app(state, title="Test App")
    static_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "/static" and isinstance(r.app, StaticFiles)
    ]
    assert len(static_mounts) == 0


def test_images_dir_not_mounted_when_missing() -> None:
    """When images_dir does not exist on disk, no /static mount is added."""
    state = _make_state()
    app = create_app(state, title="Test App", images_dir=Path("/nonexistent/images"))
    static_mounts = [
        r
        for r in app.routes
        if isinstance(r, Mount) and r.path == "/static" and isinstance(r.app, StaticFiles)
    ]
    assert len(static_mounts) == 0


# -- Extra routers --


def test_extra_routers_included() -> None:
    """Extra APIRouters passed to create_app are included in the app."""
    state = _make_state()
    router = APIRouter(prefix="/api/custom")

    @router.get("/hello")
    def hello() -> dict[str, str]:
        return {"msg": "hi"}

    app = create_app(state, title="Test App", extra_routers=[router])
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/custom/hello")
    assert response.status_code == 200
    assert response.json() == {"msg": "hi"}


def test_no_extra_routers_by_default() -> None:
    """When no extra_routers are given, only the built-in routes exist."""
    state = _make_state()
    app = create_app(state, title="Test App")
    # Should still have the .well-known route
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/.well-known/test")
    assert response.status_code == 204


# -- Lifespan --


@pytest.mark.anyio
async def test_lifespan_calls_start_and_stop() -> None:
    """The lifespan context manager calls state.ananta.start() and stop()."""
    state = _make_state()
    state.ananta.start = MagicMock()
    state.ananta.stop = MagicMock()

    app = create_app(state, title="Test App")

    # Exercise the lifespan by using TestClient as a context manager
    # TestClient triggers startup/shutdown events
    with TestClient(app):
        state.ananta.start.assert_called_once()

    state.ananta.stop.assert_called_once()


# -- Static files served correctly --


def test_static_dir_serves_html(tmp_path: Path) -> None:
    """Static files from static_dir are served with html=True (SPA support)."""
    state = _make_state()
    index = tmp_path / "index.html"
    index.write_text("<h1>SPA</h1>")

    app = create_app(state, title="Test App", static_dir=tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    # Request the root — should serve index.html
    response = client.get("/")
    assert response.status_code == 200
    assert "<h1>SPA</h1>" in response.text


def test_images_dir_serves_file(tmp_path: Path) -> None:
    """Images from images_dir are served at /static/."""
    state = _make_state()
    logo = tmp_path / "logo.txt"
    logo.write_text("logo-content")

    app = create_app(state, title="Test App", images_dir=tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/static/logo.txt")
    assert response.status_code == 200
    assert response.text == "logo-content"


# -- Startup error handling --


def test_lifespan_prints_clean_error_on_startup_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When start() raises RuntimeError, lifespan prints message and exits cleanly."""
    state = MagicMock()
    state.ananta.start.side_effect = RuntimeError(
        "Could not connect to Docker.\n\n  Tried:\n    x ..."
    )

    app = create_app(state, title="Test App")

    # The SystemExit(1) raised in lifespan gets wrapped by anyio's TaskGroup
    # into a BaseExceptionGroup, which TestClient converts to CancelledError.
    # What matters is: (a) the clean error was printed, and (b) the app did
    # not start successfully.
    with pytest.raises(BaseException):
        with TestClient(app):
            pass

    captured = capsys.readouterr()
    assert "Could not connect to Docker" in captured.err


def test_lifespan_prints_clean_error_on_missing_image(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When start() raises ImageNotFound, lifespan prints build hint and exits."""
    state = MagicMock()
    # ImageNotFound expects (message, response=..., explanation=...)
    # but we can simulate it with a plain Exception wrapping
    response = MagicMock()
    response.status_code = 404
    response.reason = "Not Found"
    state.ananta.start.side_effect = ImageNotFound(
        "404 Client Error: Not Found",
        response=response,
        explanation="No such image: ananta-sandbox:latest",
    )

    app = create_app(state, title="Test App")

    with pytest.raises(BaseException):
        with TestClient(app):
            pass

    captured = capsys.readouterr()
    assert "ananta-sandbox" in captured.err
    assert "docker build" in captured.err


def test_lifespan_prints_clean_error_on_unexpected_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When start() raises an unexpected exception, lifespan prints it cleanly."""
    state = MagicMock()
    state.ananta.start.side_effect = PermissionError("Permission denied: /var/run/docker.sock")

    app = create_app(state, title="Test App")

    with pytest.raises(BaseException):
        with TestClient(app):
            pass

    captured = capsys.readouterr()
    assert "Permission denied" in captured.err
    assert "[ananta]" in captured.err
