"""Tests for history, export, model, and context budget REST endpoints."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api
from shesha.experimental.web.session import WebConversationSession


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.download_tasks = {}
    return state


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = create_api(mock_state)
    return TestClient(app)


def test_get_history(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage._project_path.return_value = tmp_path

    # Seed a conversation via the session
    session = WebConversationSession(tmp_path)
    session.add_exchange(
        question="What is life?",
        answer="42",
        trace_id="trace-1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=1.5,
        model="test-model",
    )

    resp = client.get("/api/topics/test-topic/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["exchanges"]) == 1
    assert data["exchanges"][0]["question"] == "What is life?"


def test_get_history_preserves_document_ids(
    client: TestClient, mock_state: MagicMock, tmp_path: Path
) -> None:
    """Session stores consulted IDs under ``document_ids`` (shared naming).

    The arxiv history endpoint now uses the shared schema which keeps
    ``document_ids`` as-is.
    """
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage._project_path.return_value = tmp_path

    session = WebConversationSession(tmp_path)
    session.add_exchange(
        question="Summarise the paper",
        answer="It discusses X",
        trace_id="trace-2",
        tokens={"prompt": 20, "completion": 10, "total": 30},
        execution_time=2.0,
        model="test-model",
        document_ids=["2005.09008v1", "2401.12345"],
    )

    resp = client.get("/api/topics/test-topic/history")
    assert resp.status_code == 200
    exchange = resp.json()["exchanges"][0]
    assert exchange["document_ids"] == ["2005.09008v1", "2401.12345"]


def test_clear_history(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage._project_path.return_value = tmp_path

    session = WebConversationSession(tmp_path)
    session.add_exchange(
        question="Hello",
        answer="Hi",
        trace_id=None,
        tokens={"prompt": 5, "completion": 3, "total": 8},
        execution_time=0.5,
        model="test-model",
    )

    resp = client.delete("/api/topics/test-topic/history")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cleared"

    # Verify it was cleared on disk
    session2 = WebConversationSession(tmp_path)
    assert session2.list_exchanges() == []


def test_export_transcript(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage._project_path.return_value = tmp_path

    session = WebConversationSession(tmp_path)
    session.add_exchange(
        question="What is life?",
        answer="42",
        trace_id=None,
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=1.5,
        model="test-model",
    )

    resp = client.get("/api/topics/test-topic/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    body = resp.text
    assert "What is life?" in body
    assert "42" in body


def test_get_model(client: TestClient, mock_state: MagicMock) -> None:
    resp = client.get("/api/model")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "test-model"


def test_update_model(client: TestClient, mock_state: MagicMock) -> None:
    resp = client.put("/api/model", json={"model": "gpt-5"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "gpt-5"


def test_context_budget(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage._project_path.return_value = tmp_path

    # Mock documents
    doc = MagicMock()
    doc.content = "x" * 4000  # 4000 chars ~= 1000 tokens
    mock_state.topic_mgr._storage.load_all_documents.return_value = [doc]

    # Empty session
    WebConversationSession(tmp_path)

    # Mock max_input_tokens via litellm (route now lives in shared router)
    with patch("shesha.experimental.shared.routes.litellm") as mock_litellm:
        mock_litellm.get_model_info.return_value = {"max_input_tokens": 100000}
        resp = client.get("/api/topics/test-topic/context-budget")

    assert resp.status_code == 200
    data = resp.json()
    assert data["used_tokens"] > 0
    assert data["max_tokens"] == 100000
    assert data["level"] == "green"
    assert data["percentage"] >= 0
