"""Tests for document explorer WebSocket handler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.document_explorer.websockets import websocket_handler
from shesha.models import ParsedDocument
from shesha.rlm.trace import TokenUsage, Trace


def _make_doc(name: str) -> ParsedDocument:
    """Create a minimal ParsedDocument for testing."""
    return ParsedDocument(
        name=name,
        content=f"Content of {name}",
        format="text",
        metadata={},
        char_count=len(f"Content of {name}"),
    )


def _make_state(tmp_path: Path | None = None) -> MagicMock:
    """Create a minimal mock DocumentExplorerState."""
    state = MagicMock()
    state.model = "test-model"
    state.session.format_history_prefix.return_value = ""
    if tmp_path is not None:
        state.uploads_dir = tmp_path / "uploads"
        state.uploads_dir.mkdir(parents=True, exist_ok=True)
    else:
        state.uploads_dir = Path("/nonexistent/uploads")
    return state


def _make_app(state: MagicMock) -> FastAPI:
    """Create a minimal FastAPI app wired to the document explorer WS handler."""
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await websocket_handler(ws, state)

    return app


@pytest.fixture
def mock_state() -> MagicMock:
    return _make_state()


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = _make_app(mock_state)
    return TestClient(app)


class TestQueryDocuments:
    """Query with document_ids loads documents and returns answer."""

    def test_loads_docs_and_returns_answer(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "Document answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        mock_result.execution_time = 1.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["content.json"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What does the report say?",
                    "document_ids": ["report-a3f2"],
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
        assert complete[0]["answer"] == "Document answer"
        assert complete[0]["document_ids"] == ["report-a3f2"]


class TestEmptyDocumentIds:
    """Query with empty or missing document_ids returns error."""

    def test_error_on_empty(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": [],
                }
            )
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "select" in msg["message"].lower() or "document" in msg["message"].lower()

    def test_error_on_missing_key(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "query", "question": "What?"})
            msg = ws.receive_json()
        assert msg["type"] == "error"


class TestCancel:
    """Cancel message sets cancel_event."""

    def test_cancel_when_no_query(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cancel"})
            msg = ws.receive_json()
        assert msg["type"] == "cancelled"


class TestSessionRecordsDocumentIds:
    """Session records which project_ids were consulted."""

    def test_session_receives_project_ids(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "The answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["file.txt"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["doc-x"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        # Verify session.add_exchange was called with the document IDs
        mock_state.session.add_exchange.assert_called_once()
        call_kwargs = mock_state.session.add_exchange.call_args.kwargs
        assert call_kwargs["document_ids"] == ["doc-x"]


    def test_empty_project_excluded_from_consulted_ids(self, tmp_path: Path) -> None:
        """A project with zero documents should not appear in consulted_ids."""
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "The answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        def list_documents(pid: str) -> list[str]:
            if pid == "empty-proj":
                return []
            return ["file.txt"]

        mock_state.shesha._storage.list_documents.side_effect = list_documents
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["has-docs", "empty-proj"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["document_ids"] == ["has-docs"]

    def test_partial_doc_failure_includes_project(self, tmp_path: Path) -> None:
        """If some docs load but one raises, the project should still be consulted."""
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "The answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["good.txt", "bad.txt"]

        call_count = 0

        def get_document(pid: str, name: str) -> ParsedDocument:
            nonlocal call_count
            call_count += 1
            if name == "bad.txt":
                raise OSError("corrupt file")
            return _make_doc(name)

        mock_state.shesha._storage.get_document.side_effect = get_document
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["proj-1"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        complete = next(m for m in messages if m["type"] == "complete")
        assert complete["document_ids"] == ["proj-1"]


class TestCompleteMessageFields:
    """Query returns complete message with expected fields."""

    def test_complete_has_required_fields(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "42"
        mock_result.token_usage = TokenUsage(prompt_tokens=200, completion_tokens=100)
        mock_result.execution_time = 3.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["main.pdf"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-doc"],
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
        c = complete[0]
        assert c["answer"] == "42"
        assert c["tokens"]["prompt"] == 200
        assert c["tokens"]["completion"] == 100
        assert c["tokens"]["total"] == 300
        assert c["duration_ms"] == 3500
        assert c["document_ids"] == ["my-doc"]
        # trace_id may be None if no traces
        assert "trace_id" in c
        # document_bytes should reflect the total byte size of loaded docs
        assert "document_bytes" in c


class TestUnknownMessageType:
    """Unknown message type returns error."""

    def test_unknown_type(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "bogus"})
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "bogus" in msg["message"]


class TestNoEngine:
    """Query when RLM engine is None returns error."""

    def test_no_engine(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_project = MagicMock()
        mock_project._rlm_engine = None

        mock_state.shesha._storage.list_documents.return_value = ["main.pdf"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-doc"],
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
        err_msg = errors[0]["message"].lower()
        assert "no valid project" in err_msg or "engine" in err_msg


class TestEngineException:
    """If the RLM engine raises, error is sent."""

    def test_engine_error_sends_error(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_project = MagicMock()
        mock_project._rlm_engine.query.side_effect = RuntimeError("engine exploded")

        mock_state.shesha._storage.list_documents.return_value = ["main.pdf"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-doc"],
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


class TestMetadataContext:
    """Upload metadata (filename, content_type) is included as context."""

    def test_metadata_appended_to_question(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)

        # Write metadata file for the project
        meta_dir = mock_state.uploads_dir / "report-abc"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / "meta.json"
        meta_path.write_text(
            json.dumps({"filename": "quarterly_report.pdf", "content_type": "application/pdf"})
        )

        mock_result = MagicMock()
        mock_result.answer = "contextual answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["content.json"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What does the report say?",
                    "document_ids": ["report-abc"],
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

        # Verify metadata was included in the question
        call_args = mock_project._rlm_engine.query.call_args
        actual_question = call_args.kwargs.get("question") or call_args[1].get("question", "")
        assert "quarterly_report.pdf" in actual_question
        assert "application/pdf" in actual_question


class TestDocumentIdValidation:
    """Reject document_ids that could cause path traversal."""

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../etc/passwd",
            "../../secret",
            ".hidden",
            "foo/bar",
            "foo\\bar",
            "",
            " ",
        ],
    )
    def test_rejects_unsafe_document_id(self, bad_id: str, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": [bad_id],
                }
            )
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "invalid" in msg["message"].lower()

    def test_rejects_mixed_good_and_bad_ids(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["good-id", "../bad"],
                }
            )
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "invalid" in msg["message"].lower()


class TestNoDocsFoundInProjects:
    """Query returns error when no documents are found in any project."""

    def test_no_docs_found(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_state.shesha._storage.list_documents.return_value = []

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["empty-doc"],
                }
            )
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "document" in msg["message"].lower() or "no" in msg["message"].lower()


class TestStaleProjectId:
    """Stale project IDs should fail gracefully, not crash the handler."""

    def test_get_project_stale_sends_error(self, tmp_path: Path) -> None:
        """get_project raising ProjectNotFoundError should send error message."""
        mock_state = _make_state(tmp_path)
        mock_state.shesha._storage.list_documents.return_value = ["main.pdf"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_project.side_effect = ProjectNotFoundError("gone-doc")

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["gone-doc"],
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
        assert "no valid project" in errors[0]["message"].lower()


class TestStaleFirstProjectFallback:
    """When first project_id is stale but later ones are valid, query succeeds."""

    def test_falls_back_to_second_project(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        mock_result = MagicMock()
        mock_result.answer = "Fallback answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        # First project loads docs, second also loads docs
        mock_state.shesha._storage.list_documents.return_value = ["file.txt"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []

        # First project is stale, second exists
        def get_project(pid: str) -> MagicMock:
            if pid == "stale-doc":
                raise ProjectNotFoundError(pid)
            return mock_project

        mock_state.shesha.get_project.side_effect = get_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["stale-doc", "good-doc"],
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
        assert complete[0]["answer"] == "Fallback answer"


class TestMissingMetadataSkipped:
    """When metadata is missing for a project, context is still built."""

    def test_no_metadata_still_works(self, tmp_path: Path) -> None:
        mock_state = _make_state(tmp_path)
        # Do NOT create meta.json -- handler should still work

        mock_result = MagicMock()
        mock_result.answer = "works without meta"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["file.txt"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["no-meta-doc"],
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
        assert complete[0]["answer"] == "works without meta"
