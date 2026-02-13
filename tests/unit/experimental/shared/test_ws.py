"""Tests for shared WebSocket query handler."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from shesha.experimental.shared.websockets import websocket_handler
from shesha.models import ParsedDocument
from shesha.rlm.trace import TokenUsage, Trace

_SESSION_PATCH = "shesha.experimental.shared.websockets.WebConversationSession"


def _make_doc(name: str) -> ParsedDocument:
    """Create a minimal ParsedDocument for testing."""
    return ParsedDocument(
        name=name,
        content=f"Content of {name}",
        format="text",
        metadata={},
        char_count=len(f"Content of {name}"),
    )


def _make_state() -> MagicMock:
    """Create a minimal mock state for testing."""
    state = MagicMock()
    state.model = "test-model"
    return state


def _mock_session() -> MagicMock:
    """Create a mock session with empty history."""
    session = MagicMock()
    session.format_history_prefix.return_value = ""
    return session


def _make_app(
    state: MagicMock,
    extra_handlers: dict[str, Callable[..., object]] | None = None,
    build_context: Callable[..., str] | None = None,
) -> FastAPI:
    """Create a minimal FastAPI app wired to the shared websocket_handler."""
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await websocket_handler(
            ws, state, extra_handlers=extra_handlers, build_context=build_context
        )

    return app


@pytest.fixture
def mock_state() -> MagicMock:
    return _make_state()


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = _make_app(mock_state)
    return TestClient(app)


def test_ws_query_returns_complete(client: TestClient, mock_state: MagicMock) -> None:
    """WebSocket query returns a complete message with answer and document_ids."""
    mock_result = MagicMock()
    mock_result.answer = "The answer is 42."
    mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    mock_result.execution_time = 1.5
    mock_result.trace = Trace(steps=[])

    mock_project = MagicMock()
    mock_project._rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    mock_state.topic_mgr._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.topic_mgr._storage.list_traces.return_value = []

    with patch(_SESSION_PATCH) as mock_sess_cls:
        mock_sess_cls.return_value = _mock_session()

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "topic": "test",
                    "question": "What?",
                    "document_ids": ["doc1"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    complete = [m for m in messages if m["type"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["answer"] == "The answer is 42."
    assert complete[0]["document_ids"] == ["doc1"]


def test_ws_query_no_topic(client: TestClient, mock_state: MagicMock) -> None:
    """Query for non-existent topic returns error."""
    mock_state.topic_mgr.resolve.return_value = None
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "query", "topic": "nope", "question": "What?"})
        msg = ws.receive_json()
    assert msg["type"] == "error"


def test_ws_cancel(client: TestClient, mock_state: MagicMock) -> None:
    """Cancel message when no query is running returns cancelled."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "cancel"})
        msg = ws.receive_json()
    assert msg["type"] == "cancelled"


def test_ws_query_engine_exception_sends_error(client: TestClient, mock_state: MagicMock) -> None:
    """If the RLM engine raises, drain_task is cleaned up and error is sent."""
    mock_project = MagicMock()
    mock_project._rlm_engine.query.side_effect = RuntimeError("engine exploded")

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    mock_state.topic_mgr._storage.get_document.side_effect = lambda pid, name: _make_doc(name)

    with patch(_SESSION_PATCH) as mock_sess_cls:
        mock_sess_cls.return_value = _mock_session()

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "topic": "test",
                    "question": "What?",
                    "document_ids": ["doc1"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    errors = [m for m in messages if m["type"] == "error"]
    assert len(errors) == 1
    assert "engine exploded" in errors[0]["message"]


def test_ws_unknown_message_type(client: TestClient, mock_state: MagicMock) -> None:
    """Unknown message type returns error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "bogus"})
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "bogus" in msg["message"]


def test_ws_query_no_document_ids(client: TestClient, mock_state: MagicMock) -> None:
    """Query without document_ids returns error."""
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "query", "topic": "test", "question": "What?"})
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "document" in msg["message"].lower() or "select" in msg["message"].lower()


def test_ws_extra_handler_is_called(mock_state: MagicMock) -> None:
    """Extra handlers registered in extra_handlers dict are dispatched."""
    received: list[dict[str, object]] = []

    async def handle_custom(ws: WebSocket, data: dict[str, object], state: object) -> None:
        received.append(data)
        await ws.send_json({"type": "custom_response", "ok": True})

    app = _make_app(mock_state, extra_handlers={"custom_action": handle_custom})
    test_client = TestClient(app)

    with test_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "custom_action", "payload": "hello"})
        msg = ws.receive_json()

    assert msg["type"] == "custom_response"
    assert msg["ok"] is True
    assert len(received) == 1
    assert received[0]["payload"] == "hello"


def test_ws_build_context_called(mock_state: MagicMock) -> None:
    """build_context callback is invoked and its result appended to question."""
    mock_result = MagicMock()
    mock_result.answer = "contextual answer"
    mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
    mock_result.execution_time = 0.5
    mock_result.trace = Trace(steps=[])

    mock_project = MagicMock()
    mock_project._rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    mock_state.topic_mgr._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.topic_mgr._storage.list_traces.return_value = []

    def my_build_context(
        document_ids: list[str], state: object, loaded_docs: list[ParsedDocument]
    ) -> str:
        return "\n\nEXTRA CONTEXT"

    app = _make_app(mock_state, build_context=my_build_context)
    test_client = TestClient(app)

    with patch(_SESSION_PATCH) as mock_sess_cls:
        mock_sess_cls.return_value = _mock_session()

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "topic": "test",
                    "question": "What?",
                    "document_ids": ["doc1"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    complete = [m for m in messages if m["type"] == "complete"]
    assert len(complete) == 1

    # Verify the build_context output was included in the question
    call_args = mock_project._rlm_engine.query.call_args
    actual_question = call_args.kwargs.get("question") or call_args[1].get("question", "")
    assert "EXTRA CONTEXT" in actual_question


def test_ws_query_no_engine_sends_error(client: TestClient, mock_state: MagicMock) -> None:
    """Query when RLM engine is None returns error."""
    mock_project = MagicMock()
    mock_project._rlm_engine = None

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    mock_state.topic_mgr._storage.get_document.side_effect = lambda pid, name: _make_doc(name)

    with patch(_SESSION_PATCH) as mock_sess_cls:
        mock_sess_cls.return_value = _mock_session()

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "topic": "test",
                    "question": "What?",
                    "document_ids": ["doc1"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    errors = [m for m in messages if m["type"] == "error"]
    assert len(errors) == 1
    assert "engine" in errors[0]["message"].lower() or "configured" in errors[0]["message"].lower()
