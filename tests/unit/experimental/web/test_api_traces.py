"""Tests for traces REST endpoints."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ananta.experimental.web.api import create_api


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.download_tasks = {}
    # The arxiv TopicManager does not have resolve_all; delete it so the
    # shared router's _resolve_all_project_ids falls back to resolve().
    del state.topic_mgr.resolve_all
    return state


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = create_api(mock_state)
    return TestClient(app)


def _make_trace_file(
    tmp_path: Path, filename: str = "2025-01-15T10-30-00-123_abc12345.jsonl"
) -> Path:
    """Create a minimal trace JSONL file."""
    trace_file = tmp_path / filename
    header = {
        "type": "header",
        "trace_id": "abc12345",
        "timestamp": "2025-01-15T10:30:00Z",
        "question": "What is abiogenesis?",
        "document_ids": ["doc1"],
        "model": "gpt-5-mini",
        "system_prompt": "...",
        "subcall_prompt": "...",
    }
    step = {
        "type": "step",
        "step_type": "code_generated",
        "iteration": 0,
        "timestamp": "2025-01-15T10:30:01Z",
        "content": "print('hello')",
        "tokens_used": 150,
        "duration_ms": None,
    }
    summary = {
        "type": "summary",
        "answer": "Abiogenesis is...",
        "total_iterations": 1,
        "total_tokens": {"prompt": 100, "completion": 50},
        "total_duration_ms": 5000,
        "status": "success",
    }
    trace_file.write_text(
        json.dumps(header) + "\n" + json.dumps(step) + "\n" + json.dumps(summary) + "\n"
    )
    return trace_file


def test_list_traces(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    trace_file = _make_trace_file(tmp_path)
    mock_state.ananta.storage.list_traces.return_value = [trace_file]

    resp = client.get("/api/topics/test-topic/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["trace_id"] == "2025-01-15T10-30-00-123_abc12345"
    assert data[0]["question"] == "What is abiogenesis?"
    assert data[0]["status"] == "success"
    assert data[0]["total_tokens"] == 150


def test_list_traces_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    resp = client.get("/api/topics/nonexistent/traces")
    assert resp.status_code == 404


def test_get_trace_full(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    trace_file = _make_trace_file(tmp_path)
    mock_state.ananta.storage.list_traces.return_value = [trace_file]

    # Fetch by filename stem (what ws.py stores and frontend sends)
    resp = client.get("/api/topics/test-topic/traces/2025-01-15T10-30-00-123_abc12345")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "2025-01-15T10-30-00-123_abc12345"
    assert data["question"] == "What is abiogenesis?"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["step_type"] == "code_generated"
    assert data["status"] == "success"


def test_get_trace_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.storage.list_traces.return_value = []
    resp = client.get("/api/topics/test-topic/traces/nonexistent")
    assert resp.status_code == 404
