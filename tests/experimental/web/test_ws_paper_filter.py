"""Tests for document_ids filtering in WebSocket query handler.

These tests exercise the shared ``_handle_query`` directly with
``document_ids`` (the generic field name).  The arxiv WebSocket adapter
translates ``paper_ids`` -> ``document_ids`` at the boundary; that
translation is covered by the unit-level WebSocket tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shesha.exceptions import DocumentNotFoundError
from shesha.experimental.shared.websockets import _handle_query
from shesha.models import ParsedDocument

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


@dataclass
class FakeQueryResult:
    """Minimal query result for testing."""

    answer: str = "test answer"
    execution_time: float = 1.0
    gave_up: bool = False
    token_usage: MagicMock = field(
        default_factory=lambda: MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )


def _make_state(doc_names: list[str]) -> MagicMock:
    """Create a mock AppState with storage containing the given doc names."""
    state = MagicMock()
    state.model = "test-model"

    # topic_mgr.resolve returns a project_id
    state.topic_mgr.resolve.return_value = "proj-123"

    # Storage mock
    storage = state.shesha.storage
    storage.list_documents.return_value = doc_names
    storage.load_all_documents.return_value = [_make_doc(n) for n in doc_names]
    storage.get_document.side_effect = lambda pid, name: _make_doc(name)
    storage.list_traces.return_value = []

    # Project mock with RLM engine
    project = MagicMock()
    project.project_id = "proj-123"
    project._storage = storage
    project.rlm_engine.query.return_value = FakeQueryResult()
    project.query.return_value = FakeQueryResult()
    state.shesha.get_project.return_value = project

    return state


def _make_ws() -> AsyncMock:
    """Create a mock WebSocket."""
    ws = AsyncMock()
    return ws


class TestDocumentIdsFilterLoadsSelectedDocs:
    """When document_ids is provided, only those docs should be loaded."""

    @pytest.mark.asyncio
    async def test_document_ids_calls_get_document_for_each(self) -> None:
        """When document_ids is provided, get_document is called for each id."""
        state = _make_state(["paper-a", "paper-b", "paper-c"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": ["paper-a", "paper-c"],
        }

        with patch(_SESSION_PATCH) as mock_session_cls:
            mock_session_cls.return_value.format_history_prefix.return_value = ""
            await _handle_query(ws, data, state, threading.Event())

        storage = state.shesha.storage
        # get_document should be called for each document_id
        storage.get_document.assert_any_call("proj-123", "paper-a")
        storage.get_document.assert_any_call("proj-123", "paper-c")
        assert storage.get_document.call_count == 2

        # load_all_documents should NOT be called
        storage.load_all_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_document_ids_passes_filtered_docs_to_engine(self) -> None:
        """Filtered docs are passed to the RLM engine query."""
        state = _make_state(["paper-a", "paper-b", "paper-c"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": ["paper-b"],
        }

        with patch(_SESSION_PATCH) as mock_session_cls:
            mock_session_cls.return_value.format_history_prefix.return_value = ""
            await _handle_query(ws, data, state, threading.Event())

        project = state.shesha.get_project.return_value
        engine = project.rlm_engine

        # The engine should have been called with only the filtered doc
        engine.query.assert_called_once()
        call_kwargs = engine.query.call_args
        assert (
            call_kwargs.kwargs.get("documents") == ["Content of paper-b"]
            or call_kwargs[1].get("documents") == ["Content of paper-b"]
            or (len(call_kwargs.args) > 0 and call_kwargs.args[0] == ["Content of paper-b"])
        )

    @pytest.mark.asyncio
    async def test_empty_document_ids_sends_error(self) -> None:
        """When document_ids is an empty list, send an error -- no implicit 'all'."""
        state = _make_state(["paper-a", "paper-b"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": [],
        }

        await _handle_query(ws, data, state, threading.Event())

        storage = state.shesha.storage
        storage.load_all_documents.assert_not_called()
        storage.get_document.assert_not_called()

        error_calls = [
            c
            for c in ws.send_json.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("type") == "error"
        ]
        assert len(error_calls) == 1
        assert "select" in error_calls[0].args[0]["message"].lower()


class TestNoDocumentIdsSendsError:
    """When document_ids is absent, send error instead of querying all."""

    @pytest.mark.asyncio
    async def test_no_document_ids_sends_error(self) -> None:
        """When document_ids is absent, send an error -- no implicit 'all'."""
        state = _make_state(["paper-a", "paper-b"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
        }

        await _handle_query(ws, data, state, threading.Event())

        storage = state.shesha.storage
        storage.load_all_documents.assert_not_called()
        storage.get_document.assert_not_called()

        error_calls = [
            c
            for c in ws.send_json.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("type") == "error"
        ]
        assert len(error_calls) == 1
        assert "select" in error_calls[0].args[0]["message"].lower()


class TestCompleteMessageIncludesDocumentIds:
    """The complete WS message should include document_ids."""

    @pytest.mark.asyncio
    async def test_complete_message_contains_document_ids(self) -> None:
        """Complete message includes document_ids list from loaded docs."""
        state = _make_state(["paper-a", "paper-b", "paper-c"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": ["paper-a", "paper-c"],
        }

        with patch(_SESSION_PATCH) as mock_session_cls:
            mock_session_cls.return_value.format_history_prefix.return_value = ""
            await _handle_query(ws, data, state, threading.Event())

        complete_calls = [
            c
            for c in ws.send_json.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("type") == "complete"
        ]
        assert len(complete_calls) == 1
        complete_msg = complete_calls[0].args[0]
        assert complete_msg["document_ids"] == ["paper-a", "paper-c"]

    @pytest.mark.asyncio
    async def test_session_add_exchange_receives_document_ids(self) -> None:
        """session.add_exchange is called with document_ids."""
        state = _make_state(["paper-a", "paper-b"])
        ws = _make_ws()

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": ["paper-a"],
        }

        with patch(_SESSION_PATCH) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.format_history_prefix.return_value = ""
            await _handle_query(ws, data, state, threading.Event())

        mock_session.add_exchange.assert_called_once()
        call_kwargs = mock_session.add_exchange.call_args.kwargs
        assert call_kwargs["document_ids"] == ["paper-a"]


class TestDocumentIdsAllInvalid:
    """When document_ids are provided but none are valid, send error."""

    @pytest.mark.asyncio
    async def test_all_invalid_document_ids_sends_error(self) -> None:
        """When all document_ids refer to nonexistent docs, send an error."""
        state = _make_state(["paper-a", "paper-b"])
        ws = _make_ws()

        # Make get_document raise for unknown docs
        storage = state.shesha.storage
        storage.get_document.side_effect = DocumentNotFoundError("proj-123", "nonexistent")

        data: dict[str, object] = {
            "topic": "chess",
            "question": "What is chess?",
            "document_ids": ["nonexistent"],
        }

        with patch(_SESSION_PATCH) as mock_session_cls:
            mock_session_cls.return_value.format_history_prefix.return_value = ""
            await _handle_query(ws, data, state, threading.Event())

        # Should have sent an error about no valid documents
        error_calls = [
            c
            for c in ws.send_json.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("type") == "error"
        ]
        assert len(error_calls) == 1
        assert "no valid" in error_calls[0].args[0]["message"].lower()
