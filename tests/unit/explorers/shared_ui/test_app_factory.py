"""Tests for the shared FastAPI app factory."""

from __future__ import annotations

from pathlib import Path
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
