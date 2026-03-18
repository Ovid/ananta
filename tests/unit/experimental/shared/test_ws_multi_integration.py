"""WebSocket integration tests for handle_multi_project_query.

Safety-net tests for the multi-project handler exercised through a real
FastAPI TestClient WebSocket connection, matching the single-project
integration tests in test_ws.py.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from shesha.experimental.shared.websockets import (
    handle_multi_project_query,
    websocket_handler,
)
from shesha.models import ParsedDocument
from shesha.rlm.trace import TokenUsage


def _make_doc(name: str) -> ParsedDocument:
    return ParsedDocument(
        name=name,
        content=f"Content of {name}",
        format="text",
        metadata={},
        char_count=len(f"Content of {name}"),
    )


def _make_query_result(answer: str = "42") -> MagicMock:
    result = MagicMock()
    result.answer = answer
    result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    result.execution_time = 1.5
    return result


def _make_state(
    *,
    doc_names: list[str] | None = None,
    has_engine: bool = True,
    answer: str = "42",
) -> MagicMock:
    """Create a mock state wired for multi-project queries."""
    state = MagicMock()
    state.model = "test-model"
    state.session = MagicMock()
    state.session.format_history_prefix.return_value = ""

    storage = state.shesha._storage
    storage.list_documents.return_value = doc_names or ["doc1.txt"]
    storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    storage.list_traces.return_value = []

    project = MagicMock()
    if has_engine:
        project._rlm_engine.query.return_value = _make_query_result(answer)
    else:
        project._rlm_engine = None
    state.shesha.get_project.return_value = project

    return state


def _make_app(state: MagicMock, **multi_kwargs: object) -> FastAPI:
    """Create a FastAPI app wired to handle_multi_project_query via websocket_handler."""
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        async def query_handler(
            websocket: WebSocket,
            data: dict[str, object],
            st: object,
            cancel_event: threading.Event,
        ) -> None:
            await handle_multi_project_query(
                websocket,
                data,
                st,
                cancel_event,
                **multi_kwargs,  # type: ignore[arg-type]
            )

        await websocket_handler(ws, state, query_handler=query_handler)

    return app


def _collect_messages(ws: object) -> list[dict[str, object]]:
    """Read messages until complete or error."""
    messages = []
    while True:
        msg = ws.receive_json()  # type: ignore[attr-defined]
        messages.append(msg)
        if msg["type"] in ("complete", "error"):
            break
    return messages


class TestMultiProjectHappyPath:
    def test_returns_complete_with_answer(self) -> None:
        state = _make_state(answer="The answer is 42.")
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        complete = [m for m in messages if m["type"] == "complete"]
        assert len(complete) == 1
        assert complete[0]["answer"] == "The answer is 42."

    def test_sends_status_before_complete(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        types = [m["type"] for m in messages]
        assert "status" in types
        status_idx = types.index("status")
        complete_idx = types.index("complete")
        assert status_idx < complete_idx

    def test_complete_includes_expected_fields(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        assert "answer" in complete
        assert "tokens" in complete
        assert "duration_ms" in complete
        assert "document_ids" in complete
        assert "document_bytes" in complete
        assert "allow_background_knowledge" in complete
        assert "trace_id" in complete

    def test_document_bytes_reflects_loaded_content(self) -> None:
        state = _make_state(doc_names=["a.txt", "b.txt"])
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        expected_bytes = len(b"Content of a.txt") + len(b"Content of b.txt")
        assert complete["document_bytes"] == expected_bytes

    def test_multiple_projects_loads_docs_from_all(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj1", "proj2"],
                }
            )
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["type"] == "complete"

        # Engine should have been called with docs from both projects
        engine = state.shesha.get_project.return_value._rlm_engine
        call_kwargs = engine.query.call_args.kwargs
        # 2 projects x 1 doc each = 2 documents
        assert len(call_kwargs["documents"]) == 2

    def test_consulted_ids_are_project_ids(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj1", "proj2"],
                }
            )
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["document_ids"] == ["proj1", "proj2"]


class TestMultiProjectEngineSelection:
    def test_no_engine_sends_error(self) -> None:
        state = _make_state(has_engine=False)
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        errors = [m for m in messages if m["type"] == "error"]
        assert len(errors) == 1

    def test_first_project_get_fails_tries_next(self) -> None:
        """If get_project raises for first ID, handler tries the next."""
        state = _make_state()

        call_count = 0

        def get_project_side_effect(pid: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if pid == "bad-proj":
                raise ValueError("Project not found")
            project = MagicMock()
            project._rlm_engine.query.return_value = _make_query_result("fallback answer")
            return project

        state.shesha.get_project.side_effect = get_project_side_effect
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["bad-proj", "good-proj"],
                }
            )
            messages = _collect_messages(ws)

        complete = [m for m in messages if m["type"] == "complete"]
        assert len(complete) == 1
        assert complete[0]["answer"] == "fallback answer"

    def test_engine_query_failure_sends_error(self) -> None:
        state = _make_state()
        engine = state.shesha.get_project.return_value._rlm_engine
        engine.query.side_effect = RuntimeError("engine exploded")
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        errors = [m for m in messages if m["type"] == "error"]
        assert len(errors) == 1
        assert "failed" in errors[0]["message"].lower()


class TestMultiProjectDocumentLoading:
    def test_partial_doc_load_failure_still_queries(self) -> None:
        """If some documents fail to load, handler proceeds with the rest."""
        state = _make_state(doc_names=["good.txt", "bad.txt"])
        storage = state.shesha._storage

        def get_doc_side_effect(pid: str, name: str) -> ParsedDocument:
            if name == "bad.txt":
                raise RuntimeError("Disk error")
            return _make_doc(name)

        storage.get_document.side_effect = get_doc_side_effect
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        complete = [m for m in messages if m["type"] == "complete"]
        assert len(complete) == 1

    def test_all_docs_fail_sends_error(self) -> None:
        state = _make_state()
        storage = state.shesha._storage
        storage.get_document.side_effect = RuntimeError("Disk error")
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        errors = [m for m in messages if m["type"] == "error"]
        assert len(errors) == 1
        assert "no documents" in errors[0]["message"].lower()

    def test_list_documents_fails_skips_project(self) -> None:
        """If list_documents raises for a project, handler skips it."""
        state = _make_state()
        storage = state.shesha._storage

        call_count = 0

        def list_docs_side_effect(pid: str) -> list[str]:
            nonlocal call_count
            call_count += 1
            if pid == "broken-proj":
                raise RuntimeError("Storage error")
            return ["doc1.txt"]

        storage.list_documents.side_effect = list_docs_side_effect
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["broken-proj", "good-proj"],
                }
            )
            messages = _collect_messages(ws)

        complete = [m for m in messages if m["type"] == "complete"]
        assert len(complete) == 1


class TestMultiProjectCallbacks:
    def test_build_context_result_appended_to_question(self) -> None:
        state = _make_state()

        async def build_ctx(st: object, project_ids: list[str]) -> str:
            return "EXTRA MULTI CONTEXT"

        app = _make_app(state, item_noun="documents", build_context=build_ctx)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            _collect_messages(ws)

        engine = state.shesha.get_project.return_value._rlm_engine
        call_kwargs = engine.query.call_args.kwargs
        assert "EXTRA MULTI CONTEXT" in call_kwargs["question"]

    def test_get_session_callback_used_for_history(self) -> None:
        state = _make_state()
        custom_session = MagicMock()
        custom_session.format_history_prefix.return_value = "HISTORY: "

        def get_session(st: object, topic: str) -> MagicMock:
            return custom_session

        app = _make_app(state, item_noun="documents", get_session=get_session)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj1"],
                    "topic": "my-topic",
                }
            )
            _collect_messages(ws)

        engine = state.shesha.get_project.return_value._rlm_engine
        call_kwargs = engine.query.call_args.kwargs
        assert call_kwargs["question"].startswith("HISTORY: ")
        custom_session.add_exchange.assert_called_once()

    def test_allow_background_knowledge_passed_to_engine(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj1"],
                    "allow_background_knowledge": True,
                }
            )
            _collect_messages(ws)

        engine = state.shesha.get_project.return_value._rlm_engine
        call_kwargs = engine.query.call_args.kwargs
        assert call_kwargs["allow_background_knowledge"] is True

    def test_allow_background_knowledge_in_complete_response(self) -> None:
        state = _make_state()
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj1"],
                    "allow_background_knowledge": True,
                }
            )
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["allow_background_knowledge"] is True


class TestMultiProjectSessionRecording:
    def test_exchange_saved_to_session(self) -> None:
        state = _make_state(answer="recorded answer")
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            _collect_messages(ws)

        state.session.add_exchange.assert_called_once()
        kwargs = state.session.add_exchange.call_args.kwargs
        assert kwargs["answer"] == "recorded answer"
        assert kwargs["question"] == "What?"

    def test_trace_id_from_storage(self) -> None:
        state = _make_state()
        storage = state.shesha._storage
        storage.list_traces.return_value = [Path("/traces/abc123.jsonl")]
        app = _make_app(state, item_noun="documents")
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?", "document_ids": ["proj1"]})
            messages = _collect_messages(ws)

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["trace_id"] == "abc123"
