"""Tests for code explorer per-topic history API routes.

These tests verify the per-topic history, clear, and export endpoints work
through the shared router.  The global /api/history and /api/export routes
were removed in favour of per-topic endpoints.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ananta.explorers.code.api import create_api
from ananta.explorers.code.dependencies import (
    CodeExplorerState,
    get_topic_session,
)
from ananta.explorers.code.topics import CodeExplorerTopicManager
from ananta.explorers.shared_ui.session import WebConversationSession


@pytest.fixture
def mock_ananta(tmp_path: Path) -> MagicMock:
    """Create a mock Ananta instance."""
    ananta = MagicMock()
    ananta.list_projects.return_value = []
    ananta.storage = MagicMock()
    ananta.storage.list_documents.return_value = []
    ananta.storage.list_traces.return_value = []
    # Return a real Path so _build_repo_info's display-name lookup doesn't
    # produce a MagicMock string.  Individual tests can override this.
    ananta.storage.get_project_dir.return_value = tmp_path / "default_project_dir"
    return ananta


@pytest.fixture
def topic_mgr(tmp_path: Path) -> CodeExplorerTopicManager:
    """Create a real CodeExplorerTopicManager backed by tmp_path."""
    mgr = CodeExplorerTopicManager(tmp_path / "topics")
    mgr.create("TestTopic")
    return mgr


@pytest.fixture
def session(tmp_path: Path) -> WebConversationSession:
    """Create a real WebConversationSession backed by tmp_path."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    return WebConversationSession(session_dir)


@pytest.fixture
def state(
    mock_ananta: MagicMock,
    topic_mgr: CodeExplorerTopicManager,
    session: WebConversationSession,
) -> CodeExplorerState:
    """Create a CodeExplorerState with mock ananta and real session."""
    return CodeExplorerState(
        ananta=mock_ananta,
        topic_mgr=topic_mgr,
        session=session,
        model="test-model",
    )


@pytest.fixture
def client(state: CodeExplorerState) -> TestClient:
    """Create a FastAPI TestClient for the code explorer API."""
    app = create_api(state)
    return TestClient(app)


def _add_sample_exchange(session: WebConversationSession, q: str, a: str) -> None:
    """Helper to add a sample exchange to the session."""
    session.add_exchange(
        question=q,
        answer=a,
        trace_id="trace-123",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="test-model",
    )


# ---- GET /api/topics/{name}/history ----


class TestGetHistory:
    def test_empty_history(self, client: TestClient) -> None:
        """GET /api/topics/{name}/history returns empty exchanges list."""
        resp = client.get("/api/topics/TestTopic/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"exchanges": []}

    def test_history_with_exchanges(self, client: TestClient, state: CodeExplorerState) -> None:
        """GET /api/topics/{name}/history returns exchanges after adding some."""
        topic_session = get_topic_session(state, "TestTopic")
        _add_sample_exchange(topic_session, "What is Python?", "A programming language.")
        _add_sample_exchange(topic_session, "What is Rust?", "A systems language.")

        resp = client.get("/api/topics/TestTopic/history")
        assert resp.status_code == 200
        data = resp.json()
        exchanges = data["exchanges"]
        assert len(exchanges) == 2
        assert exchanges[0]["question"] == "What is Python?"
        assert exchanges[0]["answer"] == "A programming language."
        assert exchanges[1]["question"] == "What is Rust?"
        assert exchanges[1]["answer"] == "A systems language."


# ---- DELETE /api/topics/{name}/history ----


class TestClearHistory:
    def test_clear_history(self, client: TestClient, state: CodeExplorerState) -> None:
        """DELETE /api/topics/{name}/history clears all exchanges."""
        topic_session = get_topic_session(state, "TestTopic")
        _add_sample_exchange(topic_session, "Hello", "World")
        assert len(topic_session.list_exchanges()) == 1

        resp = client.delete("/api/topics/TestTopic/history")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cleared"}

        # Verify cleared via GET
        resp = client.get("/api/topics/TestTopic/history")
        assert resp.status_code == 200
        assert resp.json() == {"exchanges": []}

    def test_clear_empty_history(self, client: TestClient) -> None:
        """DELETE /api/topics/{name}/history on empty history succeeds."""
        resp = client.delete("/api/topics/TestTopic/history")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cleared"}


# ---- GET /api/topics/{name}/export ----


class TestExportTranscript:
    def test_export_empty(self, client: TestClient) -> None:
        """GET /api/topics/{name}/export returns markdown text even when empty."""
        resp = client.get("/api/topics/TestTopic/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "# Conversation Transcript" in resp.text

    def test_export_with_exchanges(self, client: TestClient, state: CodeExplorerState) -> None:
        """GET /api/topics/{name}/export returns markdown containing the exchanges."""
        topic_session = get_topic_session(state, "TestTopic")
        _add_sample_exchange(topic_session, "What is Python?", "A programming language.")
        _add_sample_exchange(topic_session, "What is Rust?", "A systems language.")

        resp = client.get("/api/topics/TestTopic/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        text = resp.text
        assert "# Conversation Transcript" in text
        assert "What is Python?" in text
        assert "A programming language." in text
        assert "What is Rust?" in text
        assert "A systems language." in text


# ---- Global routes removed ----


class TestGlobalRoutesRemoved:
    def test_global_history_get_returns_404(self, client: TestClient) -> None:
        """GET /api/history should no longer exist."""
        resp = client.get("/api/history")
        assert resp.status_code == 404

    def test_global_history_delete_returns_error(self, client: TestClient) -> None:
        """DELETE /api/history should no longer exist."""
        resp = client.delete("/api/history")
        # 404 when no SPA catch-all, 405 when the SPA static mount
        # intercepts the path but rejects non-GET methods.
        assert resp.status_code in (404, 405)

    def test_global_export_returns_404(self, client: TestClient) -> None:
        """GET /api/export should no longer exist."""
        resp = client.get("/api/export")
        assert resp.status_code == 404
