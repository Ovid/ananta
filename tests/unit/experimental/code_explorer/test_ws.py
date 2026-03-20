"""Tests for code explorer WebSocket handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.code_explorer.websockets import websocket_handler
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


def _make_state() -> MagicMock:
    """Create a minimal mock CodeExplorerState."""
    state = MagicMock()
    state.model = "test-model"
    state.session.format_history_prefix.return_value = ""
    return state


def _make_app(state: MagicMock) -> FastAPI:
    """Create a minimal FastAPI app wired to the code explorer WS handler."""
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


class TestQueryMultipleProjects:
    """Query with document_ids loads documents from multiple projects."""

    def test_loads_docs_from_multiple_projects(self, mock_state: MagicMock) -> None:
        """document_ids are project_ids; handler loads all docs from each."""
        mock_result = MagicMock()
        mock_result.answer = "Cross-project answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        mock_result.execution_time = 2.0
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        # Two projects, each with different docs
        def list_documents(pid: str) -> list[str]:
            if pid == "proj-a":
                return ["fileA1.py", "fileA2.py"]
            elif pid == "proj-b":
                return ["fileB1.py"]
            return []

        mock_state.shesha.storage.list_documents.side_effect = list_documents
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "How does auth work?",
                    "document_ids": ["proj-a", "proj-b"],
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
        assert complete[0]["answer"] == "Cross-project answer"
        # document_ids in complete message should be the project_ids consulted
        assert complete[0]["document_ids"] == ["proj-a", "proj-b"]

        # Verify the engine was called with docs from both projects
        call_args = mock_project.rlm_engine.query.call_args
        doc_names = call_args.kwargs.get("doc_names") or call_args[1].get("doc_names", [])
        assert "fileA1.py" in doc_names
        assert "fileA2.py" in doc_names
        assert "fileB1.py" in doc_names


class TestQueryEmptyDocumentIds:
    """Query with empty document_ids returns error."""

    def test_empty_list(self, client: TestClient) -> None:
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
        assert "select" in msg["message"].lower() or "repositor" in msg["message"].lower()

    def test_missing_key(self, client: TestClient) -> None:
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

    def test_session_receives_project_ids(self, mock_state: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.answer = "The answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        mock_state.shesha.storage.list_documents.return_value = ["file.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["repo-x"],
                }
            )
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        # Verify session.add_exchange was called with the project IDs
        mock_state.session.add_exchange.assert_called_once()
        call_kwargs = mock_state.session.add_exchange.call_args.kwargs
        assert call_kwargs["document_ids"] == ["repo-x"]


class TestCompleteMessageFields:
    """Query returns complete message with expected fields."""

    def test_complete_has_required_fields(self, mock_state: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.answer = "42"
        mock_result.token_usage = TokenUsage(prompt_tokens=200, completion_tokens=100)
        mock_result.execution_time = 3.5
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-repo"],
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
        assert c["document_ids"] == ["my-repo"]
        # trace_id may be None if no traces
        assert "trace_id" in c


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

    def test_no_engine(self, mock_state: MagicMock) -> None:
        mock_project = MagicMock()
        mock_project.rlm_engine = None

        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-repo"],
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

    def test_engine_error_sends_error(self, mock_state: MagicMock) -> None:
        mock_project = MagicMock()
        mock_project.rlm_engine.query.side_effect = RuntimeError("engine exploded")

        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["my-repo"],
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


class TestAnalysisContext:
    """Per-project analysis is included as context in the question."""

    def test_analysis_appended_to_question(self, mock_state: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.answer = "contextual answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        # Return analysis for project
        analysis = MagicMock()
        analysis.overview = "This repo implements authentication"
        mock_state.shesha.get_analysis.return_value = analysis

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "How does auth work?",
                    "document_ids": ["auth-repo"],
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

        # Verify analysis overview was included in the question
        call_args = mock_project.rlm_engine.query.call_args
        actual_question = call_args.kwargs.get("question") or call_args[1].get("question", "")
        assert "This repo implements authentication" in actual_question


class TestDocumentIdValidation:
    """Reject document_ids that could cause path traversal."""

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../etc/passwd",
            "../../secret",
            ".hidden",
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

    def test_no_docs_found(self, mock_state: MagicMock) -> None:
        mock_state.shesha.storage.list_documents.return_value = []
        mock_state.shesha.get_analysis.return_value = None

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["empty-repo"],
                }
            )
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "document" in msg["message"].lower() or "no" in msg["message"].lower()


class TestStaleProjectId:
    """Stale project IDs should fail gracefully, not crash the handler."""

    def test_get_analysis_skips_stale_project(self, mock_state: MagicMock) -> None:
        """get_analysis raising ProjectNotFoundError should be skipped."""
        mock_result = MagicMock()
        mock_result.answer = "still works"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project
        mock_state.shesha.get_analysis.side_effect = ProjectNotFoundError("stale-repo")

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["stale-repo"],
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
        assert complete[0]["answer"] == "still works"

    def test_get_project_stale_sends_error(self, mock_state: MagicMock) -> None:
        """get_project raising ProjectNotFoundError should send error message."""
        mock_state.shesha.storage.list_documents.return_value = ["main.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.get_analysis.return_value = None
        mock_state.shesha.get_project.side_effect = ProjectNotFoundError("gone-repo")

        app = _make_app(mock_state)
        test_client = TestClient(app)

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "query",
                    "question": "What?",
                    "document_ids": ["gone-repo"],
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

    def test_falls_back_to_second_project(self, mock_state: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.answer = "Fallback answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        mock_result.execution_time = 0.5
        mock_result.trace = Trace(steps=[])
        mock_result.gave_up = False

        mock_project = MagicMock()
        mock_project.rlm_engine.query.return_value = mock_result

        mock_state.shesha.storage.list_documents.return_value = ["file.py"]
        mock_state.shesha.storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha.storage.list_traces.return_value = []
        mock_state.shesha.get_analysis.return_value = None

        def get_project(pid: str) -> MagicMock:
            if pid == "stale-repo":
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
                    "document_ids": ["stale-repo", "good-repo"],
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
