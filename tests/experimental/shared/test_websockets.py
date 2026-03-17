"""Tests for shared WebSocket handler security hardening."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shesha.experimental.shared.websockets import _handle_query, handle_multi_project_query


def _make_ws() -> AsyncMock:
    """Build a mock WebSocket that records sent JSON messages."""
    ws = AsyncMock()
    ws.sent: list[dict] = []

    async def _send_json(data: dict) -> None:
        ws.sent.append(data)

    ws.send_json = AsyncMock(side_effect=_send_json)
    return ws


def _make_state() -> MagicMock:
    """Build a minimal mock state for _handle_query."""
    state = MagicMock()
    state.topic_mgr.resolve.return_value = "proj-1"
    state.topic_mgr._storage.list_documents.return_value = ["doc-a"]
    state.topic_mgr._storage.get_document.return_value = MagicMock(
        name="doc-a", content="hello"
    )
    state.topic_mgr._storage._project_path.return_value = "/tmp/proj"
    state.topic_mgr._storage.list_traces.return_value = []
    state.model = "test-model"

    # RLM engine mock
    engine = MagicMock()
    project = MagicMock()
    project._rlm_engine = engine
    state.shesha.get_project.return_value = project

    return state


class TestHandleQueryDocIdValidation:
    """I5: _handle_query must validate document_ids against _SAFE_ID_RE."""

    @pytest.mark.asyncio
    async def test_rejects_path_traversal_in_document_id(self) -> None:
        ws = _make_ws()
        state = _make_state()
        cancel = threading.Event()

        data = {
            "topic": "my-topic",
            "question": "hello",
            "document_ids": ["../../../etc/passwd"],
        }

        await _handle_query(ws, data, state, cancel)

        error_msgs = [m for m in ws.sent if m.get("type") == "error"]
        assert len(error_msgs) == 1
        assert "invalid" in error_msgs[0]["message"].lower() or "Invalid" in error_msgs[0]["message"]
        # Must NOT reach the storage layer
        state.topic_mgr._storage.get_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_document_id_with_special_chars(self) -> None:
        ws = _make_ws()
        state = _make_state()
        cancel = threading.Event()

        data = {
            "topic": "my-topic",
            "question": "hello",
            "document_ids": ["valid-doc", "bad id with spaces"],
        }

        await _handle_query(ws, data, state, cancel)

        error_msgs = [m for m in ws.sent if m.get("type") == "error"]
        assert len(error_msgs) == 1
        state.topic_mgr._storage.get_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_valid_document_ids(self) -> None:
        ws = _make_ws()
        state = _make_state()
        cancel = threading.Event()

        # Mock the session to avoid filesystem access
        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""

        data = {
            "topic": "my-topic",
            "question": "hello",
            "document_ids": ["valid-doc.txt", "another_doc-2"],
        }

        with patch(
            "shesha.experimental.shared.websockets.WebConversationSession",
            return_value=mock_session,
        ):
            # Make the query raise to short-circuit execution after validation
            project = state.shesha.get_project.return_value
            project._rlm_engine.query.side_effect = RuntimeError("stop here")
            await _handle_query(ws, data, state, cancel)

        # Should have reached the storage layer (validation passed)
        assert state.topic_mgr._storage.get_document.call_count >= 1


class TestHandleQueryExceptionLeakage:
    """I6: Exception details must not leak to WebSocket clients."""

    @pytest.mark.asyncio
    async def test_masks_exception_details_in_handle_query(self) -> None:
        ws = _make_ws()
        state = _make_state()
        cancel = threading.Event()

        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""

        data = {
            "topic": "my-topic",
            "question": "hello",
            "document_ids": ["valid-doc"],
        }

        sensitive_message = "ConnectionError: failed to connect to /internal/db:5432 with password=s3cret"
        project = state.shesha.get_project.return_value
        project._rlm_engine.query.side_effect = RuntimeError(sensitive_message)

        with patch(
            "shesha.experimental.shared.websockets.WebConversationSession",
            return_value=mock_session,
        ):
            await _handle_query(ws, data, state, cancel)

        error_msgs = [m for m in ws.sent if m.get("type") == "error"]
        assert len(error_msgs) == 1
        # The sensitive message must NOT appear in the client-facing error
        assert sensitive_message not in error_msgs[0]["message"]
        assert "/internal/db:5432" not in error_msgs[0]["message"]
        assert "s3cret" not in error_msgs[0]["message"]

    @pytest.mark.asyncio
    async def test_masks_exception_details_in_multi_project_query(self) -> None:
        ws = _make_ws()
        state = MagicMock()
        cancel = threading.Event()

        # Set up state for multi-project handler
        storage = MagicMock()
        state.shesha._storage = storage
        storage.list_documents.return_value = ["doc-a"]
        storage.get_document.return_value = MagicMock(name="doc-a", content="hello")

        project = MagicMock()
        engine = MagicMock()
        sensitive_message = "OSError: /opt/shesha/config.yaml not found"
        engine.query.side_effect = RuntimeError(sensitive_message)
        project._rlm_engine = engine
        state.shesha.get_project.return_value = project
        state.session = MagicMock()
        state.session.format_history_prefix.return_value = ""

        data = {
            "topic": "my-topic",
            "question": "hello",
            "document_ids": ["projA"],
        }

        await handle_multi_project_query(ws, data, state, cancel)

        error_msgs = [m for m in ws.sent if m.get("type") == "error"]
        assert len(error_msgs) == 1
        assert sensitive_message not in error_msgs[0]["message"]
        assert "/opt/shesha/config.yaml" not in error_msgs[0]["message"]
