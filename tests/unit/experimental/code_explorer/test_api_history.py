"""Tests for code explorer global history API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.session import WebConversationSession


@pytest.fixture
def mock_shesha() -> MagicMock:
    """Create a mock Shesha instance."""
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha._storage = MagicMock()
    shesha._storage.list_documents.return_value = []
    return shesha


@pytest.fixture
def topic_mgr(tmp_path: Path) -> CodeExplorerTopicManager:
    """Create a real CodeExplorerTopicManager backed by tmp_path."""
    return CodeExplorerTopicManager(tmp_path / "topics")


@pytest.fixture
def session(tmp_path: Path) -> WebConversationSession:
    """Create a real WebConversationSession backed by tmp_path."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    return WebConversationSession(session_dir)


@pytest.fixture
def state(
    mock_shesha: MagicMock,
    topic_mgr: CodeExplorerTopicManager,
    session: WebConversationSession,
) -> CodeExplorerState:
    """Create a CodeExplorerState with mock shesha and real session."""
    return CodeExplorerState(
        shesha=mock_shesha,
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


# ---- GET /api/history ----


class TestGetHistory:
    def test_empty_history(self, client: TestClient) -> None:
        """GET /api/history returns empty exchanges list when no history."""
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"exchanges": []}

    def test_history_with_exchanges(
        self, client: TestClient, session: WebConversationSession
    ) -> None:
        """GET /api/history returns exchanges after adding some."""
        _add_sample_exchange(session, "What is Python?", "A programming language.")
        _add_sample_exchange(session, "What is Rust?", "A systems language.")

        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        exchanges = data["exchanges"]
        assert len(exchanges) == 2
        assert exchanges[0]["question"] == "What is Python?"
        assert exchanges[0]["answer"] == "A programming language."
        assert exchanges[1]["question"] == "What is Rust?"
        assert exchanges[1]["answer"] == "A systems language."


# ---- DELETE /api/history ----


class TestClearHistory:
    def test_clear_history(self, client: TestClient, session: WebConversationSession) -> None:
        """DELETE /api/history clears all exchanges."""
        _add_sample_exchange(session, "Hello", "World")
        assert len(session.list_exchanges()) == 1

        resp = client.delete("/api/history")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cleared"}

        # Verify cleared via GET
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == {"exchanges": []}

    def test_clear_empty_history(self, client: TestClient) -> None:
        """DELETE /api/history on empty history succeeds."""
        resp = client.delete("/api/history")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cleared"}


# ---- GET /api/export ----


class TestExportTranscript:
    def test_export_empty(self, client: TestClient) -> None:
        """GET /api/export returns markdown text even when empty."""
        resp = client.get("/api/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "# Conversation Transcript" in resp.text

    def test_export_with_exchanges(
        self, client: TestClient, session: WebConversationSession
    ) -> None:
        """GET /api/export returns markdown containing the exchanges."""
        _add_sample_exchange(session, "What is Python?", "A programming language.")
        _add_sample_exchange(session, "What is Rust?", "A systems language.")

        resp = client.get("/api/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        text = resp.text
        assert "# Conversation Transcript" in text
        assert "What is Python?" in text
        assert "A programming language." in text
        assert "What is Rust?" in text
        assert "A systems language." in text
