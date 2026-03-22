"""Tests for shared WebSocket query handler."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from ananta.explorers.shared_ui.websockets import build_complete_response, websocket_handler
from ananta.models import ParsedDocument
from ananta.rlm.trace import TokenUsage, Trace

_SESSION_PATCH = "ananta.explorers.shared_ui.websockets.WebConversationSession"


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
    session_factory: Callable[..., object] | None = None,
    query_handler: Callable[..., object] | None = None,
) -> FastAPI:
    """Create a minimal FastAPI app wired to the shared websocket_handler."""
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        kwargs: dict[str, object] = {}
        if extra_handlers is not None:
            kwargs["extra_handlers"] = extra_handlers
        if build_context is not None:
            kwargs["build_context"] = build_context
        if session_factory is not None:
            kwargs["session_factory"] = session_factory
        if query_handler is not None:
            kwargs["query_handler"] = query_handler
        await websocket_handler(ws, state, **kwargs)  # type: ignore[arg-type]

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
    mock_result.gave_up = False

    mock_project = MagicMock()
    mock_project.rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.ananta.storage.list_traces.return_value = []

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
    # document_bytes = total UTF-8 byte size of consulted documents
    assert complete[0]["document_bytes"] == len(b"Content of doc1")


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
    mock_project.rlm_engine.query.side_effect = RuntimeError("engine exploded")

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)

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
    assert "query execution failed" in errors[0]["message"].lower()


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
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
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
    mock_result.gave_up = False

    mock_project = MagicMock()
    mock_project.rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.ananta.storage.list_traces.return_value = []

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
    call_args = mock_project.rlm_engine.query.call_args
    actual_question = call_args.kwargs.get("question") or call_args[1].get("question", "")
    assert "EXTRA CONTEXT" in actual_question


def test_ws_query_no_engine_sends_error(client: TestClient, mock_state: MagicMock) -> None:
    """Query when RLM engine is None returns error."""
    mock_project = MagicMock()
    mock_project.rlm_engine = None

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)

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


def test_ws_session_factory_is_used(mock_state: MagicMock) -> None:
    """When session_factory is provided, it is used instead of the default."""
    mock_result = MagicMock()
    mock_result.answer = "custom session answer"
    mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
    mock_result.execution_time = 0.5
    mock_result.trace = Trace(steps=[])
    mock_result.gave_up = False

    mock_project = MagicMock()
    mock_project.rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.ananta.storage.list_traces.return_value = []

    custom_session = _mock_session()
    custom_factory = MagicMock(return_value=custom_session)

    app = _make_app(mock_state, session_factory=custom_factory)
    test_client = TestClient(app)

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

    # The custom factory should have been called (not the default)
    custom_factory.assert_called_once()
    # And the session it returned should have been used for add_exchange
    custom_session.add_exchange.assert_called_once()


def test_ws_query_handler_callback_is_called(mock_state: MagicMock) -> None:
    """When query_handler is provided, it is called instead of the default handler."""
    received_data: list[dict[str, object]] = []

    async def custom_query_handler(
        ws: WebSocket,
        data: dict[str, object],
        state: object,
        cancel_event: threading.Event,
    ) -> None:
        received_data.append(data)
        await ws.send_json({"type": "complete", "answer": "custom handler"})

    app = _make_app(mock_state, query_handler=custom_query_handler)
    test_client = TestClient(app)

    with test_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "query", "question": "What?"})
        msg = ws.receive_json()

    assert msg["type"] == "complete"
    assert msg["answer"] == "custom handler"
    assert len(received_data) == 1
    assert received_data[0]["question"] == "What?"


def test_ws_query_passes_allow_background_knowledge(
    client: TestClient, mock_state: MagicMock
) -> None:
    """WebSocket query passes allow_background_knowledge to engine."""
    mock_result = MagicMock()
    mock_result.answer = "Augmented answer."
    mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    mock_result.execution_time = 1.0
    mock_result.trace = Trace(steps=[])
    mock_result.gave_up = False

    mock_project = MagicMock()
    mock_project.rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.ananta.storage.list_traces.return_value = []

    with patch(_SESSION_PATCH) as mock_sess_cls:
        mock_sess_cls.return_value = _mock_session()

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "topic": "test",
                    "question": "What?",
                    "document_ids": ["doc1"],
                    "allow_background_knowledge": True,
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    call_kwargs = mock_project.rlm_engine.query.call_args
    assert call_kwargs.kwargs.get("allow_background_knowledge") is True

    # Verify complete message includes allow_background_knowledge
    complete = [m for m in messages if m["type"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["allow_background_knowledge"] is True


def test_ws_complete_includes_allow_background_knowledge_false(
    client: TestClient, mock_state: MagicMock
) -> None:
    """Complete message includes allow_background_knowledge=false by default."""
    mock_result = MagicMock()
    mock_result.answer = "Answer."
    mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
    mock_result.execution_time = 0.5
    mock_result.trace = Trace(steps=[])
    mock_result.gave_up = False

    mock_project = MagicMock()
    mock_project.rlm_engine.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.ananta.get_project.return_value = mock_project
    mock_state.ananta.storage.list_documents.return_value = ["doc1"]
    mock_state.ananta.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    mock_state.ananta.storage.list_traces.return_value = []

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
    assert complete[0]["allow_background_knowledge"] is False


def test_ws_new_query_cancels_previous_task(mock_state: MagicMock) -> None:
    """Sending a second query cancels and awaits the first before starting it."""
    # Gate to block the first query until we've sent the second
    gate = threading.Event()
    handler_calls: list[str] = []

    async def slow_query_handler(
        ws: WebSocket,
        data: dict[str, object],
        state: object,
        cancel_event: threading.Event,
    ) -> None:
        label = str(data.get("label", ""))
        handler_calls.append(f"start:{label}")
        loop = asyncio.get_running_loop()
        try:
            # Block until gate is opened (simulates long-running query)
            await loop.run_in_executor(None, gate.wait)
            handler_calls.append(f"complete:{label}")
            await ws.send_json({"type": "complete", "answer": label})
        except asyncio.CancelledError:
            handler_calls.append(f"cancelled:{label}")
            raise

    app = _make_app(mock_state, query_handler=slow_query_handler)
    test_client = TestClient(app)

    with test_client.websocket_connect("/ws") as ws:
        # Send first query — handler will block on gate
        ws.send_json({"type": "query", "label": "first", "question": "Q1"})
        # Send second query — should cancel the first
        ws.send_json({"type": "query", "label": "second", "question": "Q2"})
        # Open the gate so the second query can complete
        gate.set()
        # Collect messages until we get complete
        messages = []
        while True:
            msg = ws.receive_json()
            messages.append(msg)
            if msg["type"] in ("complete", "error"):
                break

    # The first handler should have been cancelled
    assert "cancelled:first" in handler_calls
    # The second should have completed
    assert "complete:second" in handler_calls
    # Only one complete message from the second query
    completes = [m for m in messages if m["type"] == "complete"]
    assert len(completes) == 1
    assert completes[0]["answer"] == "second"


class TestBuildCompleteResponse:
    """Tests for the shared build_complete_response helper."""

    def test_builds_expected_fields(self) -> None:
        """Response contains all required fields with correct values."""
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
        resp = build_complete_response(
            answer="42",
            trace_id="t-001",
            token_usage=usage,
            execution_time=1.5,
            document_ids=["doc-a", "doc-b"],
            document_bytes=1024,
            allow_background_knowledge=True,
        )
        assert resp == {
            "type": "complete",
            "answer": "42",
            "trace_id": "t-001",
            "tokens": {"prompt": 10, "completion": 20, "total": 30},
            "duration_ms": 1500,
            "document_ids": ["doc-a", "doc-b"],
            "document_bytes": 1024,
            "allow_background_knowledge": True,
            "gave_up": False,
        }

    def test_includes_gave_up_field(self) -> None:
        """Response includes gave_up field."""
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
        resp = build_complete_response(
            answer="Partial findings.",
            trace_id="t-001",
            token_usage=usage,
            execution_time=1.5,
            document_ids=["doc-a"],
            document_bytes=512,
            allow_background_knowledge=False,
            gave_up=True,
        )
        assert resp["gave_up"] is True

    def test_gave_up_defaults_to_false(self) -> None:
        """gave_up defaults to False when not provided."""
        usage = TokenUsage()
        resp = build_complete_response(
            answer="Full answer.",
            trace_id=None,
            token_usage=usage,
            execution_time=0.5,
            document_ids=[],
            document_bytes=0,
            allow_background_knowledge=False,
        )
        assert resp["gave_up"] is False

    def test_truncates_duration_ms(self) -> None:
        """duration_ms is truncated to int, not rounded."""
        usage = TokenUsage()
        resp = build_complete_response(
            answer="x",
            trace_id=None,
            token_usage=usage,
            execution_time=0.9999,
            document_ids=[],
            document_bytes=0,
            allow_background_knowledge=False,
        )
        assert resp["duration_ms"] == 999
