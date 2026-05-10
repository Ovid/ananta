"""Tests for shared API routes (topics, traces, history, model, context-budget)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ananta.explorers.shared_ui.routes import create_shared_router
from ananta.explorers.shared_ui.session import WebConversationSession
from ananta.explorers.shared_ui.topics import BaseTopicManager


@dataclass
class FakeTopicInfo:
    """Lightweight stand-in for the domain TopicInfo dataclass.

    Matches the attributes accessed by ``create_shared_router``:
    ``name``, ``document_count``, ``formatted_size``, ``project_id``.
    """

    name: str
    document_count: int
    formatted_size: str
    project_id: str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    # By default, the topic manager does NOT have resolve_all (single-project).
    # Tests that need multi-project explicitly set state.topic_mgr.resolve_all.
    del state.topic_mgr.resolve_all
    return state


def _make_app(state: MagicMock, **kwargs: object) -> FastAPI:
    """Build a minimal FastAPI app with the shared router."""
    app = FastAPI()
    router = create_shared_router(state, **kwargs)  # type: ignore[arg-type]
    app.include_router(router)
    return app


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    """Client with all optional route groups enabled."""
    app = _make_app(mock_state)
    return TestClient(app)


@pytest.fixture
def client_no_history(mock_state: MagicMock) -> TestClient:
    """Client with per-topic history routes disabled."""
    app = _make_app(mock_state, include_per_topic_history=False)
    return TestClient(app)


@pytest.fixture
def client_no_budget(mock_state: MagicMock) -> TestClient:
    """Client with context-budget route disabled."""
    app = _make_app(mock_state, include_context_budget=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Topic CRUD
# ---------------------------------------------------------------------------


def test_list_topics_empty(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.list_topics.return_value = []
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_topics(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.list_topics.return_value = [
        FakeTopicInfo(
            name="Abiogenesis",
            document_count=5,
            formatted_size="1.0 MB",
            project_id="2025-01-15-abiogenesis",
        ),
    ]
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Abiogenesis"
    assert data[0]["document_count"] == 5


def test_create_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    # ``BaseTopicManager.create`` is annotated ``-> None`` (it does not
    # return a slug); the route must therefore not depend on its return
    # value (I3). Mirror the real contract here so a regression that
    # leaks ``null`` into the response body fails this test.
    mock_state.topic_mgr.create.return_value = None
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 201
    mock_state.topic_mgr.create.assert_called_once_with("Chess")
    body = resp.json()
    assert body["name"] == "Chess"
    # project_id must be a non-empty string. Previously the route
    # assigned ``BaseTopicManager.create()``'s return value (None) to
    # project_id, so every explorer using ``include_topic_crud=True``
    # got ``{"project_id": null}`` — which the FE used as a React key,
    # collapsing all topics onto a single "null" key.
    assert isinstance(body["project_id"], str)
    assert body["project_id"]


def test_create_topic_already_exists(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "existing-id"
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 409


def test_rename_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 200
    mock_state.topic_mgr.rename.assert_called_once()


def test_rename_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.rename.side_effect = ValueError("not found")
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 404


def test_rename_topic_already_exists_returns_409(
    client: TestClient, mock_state: MagicMock
) -> None:
    """``create_shared_router.rename_topic`` must map ValueError to the
    same status taxonomy as ``create_item_router.rename_topic`` (S41).

    Previously the shared router hardcoded 404 for ALL ValueError, so
    a "Topic '<x>' already exists" conflict from the topic manager was
    leaked as 404 — the FE displayed it as "topic not found", the wrong
    UX. ``_topic_error_to_status`` maps it to 409.
    """
    mock_state.topic_mgr.rename.side_effect = ValueError("Topic 'Beta' already exists")
    resp = client.patch("/api/topics/alpha", json={"new_name": "Beta"})
    assert resp.status_code == 409


def test_rename_topic_validation_error_returns_422(
    client: TestClient, mock_state: MagicMock
) -> None:
    """A validation ValueError (e.g. control bytes, slug collision) maps
    to 422 — not 404 (S41)."""
    mock_state.topic_mgr.rename.side_effect = ValueError(
        "Topic name must not contain control characters: 'bad\\x00name'"
    )
    resp = client.patch("/api/topics/alpha", json={"new_name": "bad\x00name"})
    assert resp.status_code == 422


def test_delete_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.delete("/api/topics/chess")
    assert resp.status_code == 200
    mock_state.topic_mgr.delete.assert_called_once()


def test_delete_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.delete.side_effect = ValueError("not found")
    resp = client.delete("/api/topics/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


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


def test_list_traces_multi_project(
    client: TestClient, mock_state: MagicMock, tmp_path: Path
) -> None:
    """When a topic resolves to multiple project_ids, traces are aggregated."""
    # resolve returns a single project, resolve_all returns all
    mock_state.topic_mgr.resolve.return_value = "proj-a"
    mock_state.topic_mgr.resolve_all = MagicMock(return_value=["proj-a", "proj-b"])

    (tmp_path / "a").mkdir(exist_ok=True)
    trace_a = _make_trace_file(tmp_path / "a", "2025-01-15T10-30-00-123_aaa.jsonl")

    (tmp_path / "b").mkdir(exist_ok=True)
    trace_b = _make_trace_file(tmp_path / "b", "2025-01-16T10-30-00-123_bbb.jsonl")

    def mock_list_traces(project_id: str) -> list[Path]:
        if project_id == "proj-a":
            return [trace_a]
        if project_id == "proj-b":
            return [trace_b]
        return []

    mock_state.ananta.storage.list_traces.side_effect = mock_list_traces

    resp = client.get("/api/topics/test-topic/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Should be sorted by timestamp
    assert data[0]["timestamp"] <= data[1]["timestamp"]


def test_get_trace_full(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    trace_file = _make_trace_file(tmp_path)
    mock_state.ananta.storage.list_traces.return_value = [trace_file]

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


# ---------------------------------------------------------------------------
# History & Export (per-topic, optional)
# ---------------------------------------------------------------------------


def test_get_history(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.storage.get_project_dir.return_value = tmp_path

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


def test_clear_history(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.storage.get_project_dir.return_value = tmp_path

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
    mock_state.ananta.storage.get_project_dir.return_value = tmp_path

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


def test_history_routes_excluded_when_disabled(
    client_no_history: TestClient, mock_state: MagicMock
) -> None:
    """When include_per_topic_history=False, history/export routes return 404/405."""
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client_no_history.get("/api/topics/test-topic/history")
    # Route does not exist at all, so 404 or 405
    assert resp.status_code in (404, 405)


def test_export_route_excluded_when_history_disabled(
    client_no_history: TestClient, mock_state: MagicMock
) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client_no_history.get("/api/topics/test-topic/export")
    assert resp.status_code in (404, 405)


def test_clear_history_excluded_when_disabled(
    client_no_history: TestClient, mock_state: MagicMock
) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client_no_history.delete("/api/topics/test-topic/history")
    assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Context Budget (optional)
# ---------------------------------------------------------------------------


def test_context_budget(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.storage.get_project_dir.return_value = tmp_path

    # Empty session
    WebConversationSession(tmp_path)

    with patch("ananta.explorers.shared_ui.routes.litellm") as mock_litellm:
        mock_litellm.get_model_info.return_value = {"max_input_tokens": 100000}
        resp = client.get("/api/topics/test-topic/context-budget")

    assert resp.status_code == 200
    data = resp.json()
    assert data["used_tokens"] > 0
    assert data["max_tokens"] == 100000
    assert data["level"] == "green"
    assert data["percentage"] >= 0


def test_context_budget_uses_named_constants(
    client: TestClient, mock_state: MagicMock, tmp_path: Path
) -> None:
    """Context budget calculation uses named constants, not magic numbers."""
    from ananta.explorers.shared_ui.routes import (
        BASE_PROMPT_TOKENS,
        CHARS_PER_TOKEN,
        DEFAULT_MAX_CONTEXT_TOKENS,
    )

    assert BASE_PROMPT_TOKENS == 2000
    assert CHARS_PER_TOKEN == 4
    assert DEFAULT_MAX_CONTEXT_TOKENS == 128000

    # Verify the constants are actually used in the calculation
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.storage.get_project_dir.return_value = tmp_path
    WebConversationSession(tmp_path)

    with patch("ananta.explorers.shared_ui.routes.litellm") as mock_litellm:
        mock_litellm.get_model_info.side_effect = Exception("no model info")
        resp = client.get("/api/topics/test-topic/context-budget")

    data = resp.json()
    # When litellm fails, should fall back to DEFAULT_MAX_CONTEXT_TOKENS
    assert data["max_tokens"] == DEFAULT_MAX_CONTEXT_TOKENS


def test_context_budget_excluded_when_disabled(
    client_no_budget: TestClient, mock_state: MagicMock
) -> None:
    """When include_context_budget=False, the route returns 404/405."""
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client_no_budget.get("/api/topics/test-topic/context-budget")
    assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Trace for multi-project via get_trace
# ---------------------------------------------------------------------------


def test_get_trace_multi_project(client: TestClient, mock_state: MagicMock, tmp_path: Path) -> None:
    """get_trace should search across all projects for the topic."""
    mock_state.topic_mgr.resolve.return_value = "proj-a"
    mock_state.topic_mgr.resolve_all = MagicMock(return_value=["proj-a", "proj-b"])

    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)

    trace_b = _make_trace_file(tmp_path / "b", "2025-01-16T10-30-00-123_bbb.jsonl")

    def mock_list_traces(project_id: str) -> list[Path]:
        if project_id == "proj-a":
            return []
        if project_id == "proj-b":
            return [trace_b]
        return []

    mock_state.ananta.storage.list_traces.side_effect = mock_list_traces

    resp = client.get("/api/topics/test-topic/traces/2025-01-16T10-30-00-123_bbb")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "2025-01-16T10-30-00-123_bbb"


# ---------------------------------------------------------------------------
# _topic_error_to_status
# ---------------------------------------------------------------------------


class TestTopicErrorToStatus:
    def test_already_exists_returns_409(self) -> None:
        from ananta.explorers.shared_ui.routes import _topic_error_to_status

        assert _topic_error_to_status(ValueError("Topic 'X' already exists")) == 409

    def test_not_found_returns_404(self) -> None:
        from ananta.explorers.shared_ui.routes import _topic_error_to_status

        assert _topic_error_to_status(ValueError("Topic not found: X")) == 404

    def test_slug_collision_returns_422(self) -> None:
        from ananta.explorers.shared_ui.routes import _topic_error_to_status

        msg = (
            "A topic with a different display name already uses "
            "slug 'foo': existing 'Foo' vs requested 'FOO'"
        )
        assert _topic_error_to_status(ValueError(msg)) == 422

    def test_other_error_returns_422(self) -> None:
        from ananta.explorers.shared_ui.routes import _topic_error_to_status

        assert _topic_error_to_status(ValueError("empty slug")) == 422


# ---------------------------------------------------------------------------
# create_item_router
# ---------------------------------------------------------------------------


class TestCreateItemRouter:
    @pytest.fixture
    def topic_mgr(self, tmp_path: Path) -> BaseTopicManager:
        return BaseTopicManager(tmp_path / "topics")

    @pytest.fixture
    def client(self, topic_mgr: BaseTopicManager) -> TestClient:
        from ananta.explorers.shared_ui.routes import create_item_router

        app = FastAPI()
        router = create_item_router(topic_mgr)
        app.include_router(router)
        return TestClient(app)

    def test_create_topic(self, client: TestClient) -> None:
        resp = client.post("/api/topics", json={"name": "Research"})
        assert resp.status_code == 201

    def test_create_topic_invalid_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/topics", json={"name": "!!!"})
        assert resp.status_code == 422

    def test_list_topics(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Alpha")
        topic_mgr.create("Beta")
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert sorted(names) == ["Alpha", "Beta"]

    def test_rename_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Old")
        resp = client.patch("/api/topics/Old", json={"new_name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_rename_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.patch("/api/topics/Ghost", json={"new_name": "New"})
        assert resp.status_code == 404

    def test_delete_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Doomed")
        resp = client.delete("/api/topics/Doomed")
        assert resp.status_code == 200
        assert topic_mgr.list_topics() == []

    def test_add_item_to_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        resp = client.post("/api/topics/Research/items/proj-1")
        assert resp.status_code == 200
        assert "proj-1" in topic_mgr.list_items("Research")

    def test_add_item_auto_creates_topic(
        self, client: TestClient, topic_mgr: BaseTopicManager
    ) -> None:
        resp = client.post("/api/topics/NewTopic/items/proj-1")
        assert resp.status_code == 200
        assert "NewTopic" in topic_mgr.list_topics()

    def test_remove_item_from_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "proj-1")
        resp = client.delete("/api/topics/Research/items/proj-1")
        assert resp.status_code == 200
        assert topic_mgr.list_items("Research") == []

    def test_remove_nonexistent_item_returns_404(
        self, client: TestClient, topic_mgr: BaseTopicManager
    ) -> None:
        topic_mgr.create("Research")
        resp = client.delete("/api/topics/Research/items/ghost")
        assert resp.status_code == 404

    def test_reorder_items(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "doc-1")
        topic_mgr.add_item("Research", "doc-2")
        topic_mgr.add_item("Research", "doc-3")
        resp = client.put(
            "/api/topics/Research/items/order",
            json={"item_ids": ["doc-3", "doc-1", "doc-2"]},
        )
        assert resp.status_code == 200
        assert topic_mgr.list_items("Research") == ["doc-3", "doc-1", "doc-2"]

    def test_reorder_items_topic_not_found(self, client: TestClient) -> None:
        resp = client.put(
            "/api/topics/NoSuch/items/order",
            json={"item_ids": ["doc-1"]},
        )
        assert resp.status_code == 404

    def test_reorder_items_mismatched_ids(
        self, client: TestClient, topic_mgr: BaseTopicManager
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "doc-1")
        resp = client.put(
            "/api/topics/Research/items/order",
            json={"item_ids": ["doc-1", "doc-2"]},
        )
        assert resp.status_code == 422
