"""Tests for shared multi-project WebSocket handler."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from ananta.experimental.shared.websockets import handle_multi_project_query


@pytest.fixture
def mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.session = MagicMock()
    state.session.format_history_prefix.return_value = ""
    state.ananta.storage.list_documents.return_value = ["doc1.txt"]
    doc = MagicMock()
    doc.content = "Hello"
    doc.name = "doc1.txt"
    state.ananta.storage.get_document.return_value = doc
    project = MagicMock()
    project.rlm_engine = MagicMock()
    result = MagicMock()
    result.answer = "42"
    result.token_usage.prompt_tokens = 10
    result.token_usage.completion_tokens = 5
    result.token_usage.total_tokens = 15
    result.execution_time = 1.5
    result.gave_up = False
    project.rlm_engine.query.return_value = result
    state.ananta.get_project.return_value = project
    state.ananta.storage.list_traces.return_value = []
    return state


class TestValidation:
    @pytest.mark.asyncio
    async def test_empty_document_ids_sends_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        data: dict[str, object] = {"question": "hi", "document_ids": []}
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
        )
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_id_sends_error(self, mock_ws: AsyncMock, mock_state: MagicMock) -> None:
        data: dict[str, object] = {"question": "hi", "document_ids": ["../evil"]}
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
        )
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_missing_document_ids_sends_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        data: dict[str, object] = {"question": "hi"}
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="repositories",
        )
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "repositories" in msg["message"]

    @pytest.mark.asyncio
    async def test_item_noun_appears_in_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        data: dict[str, object] = {"question": "hi", "document_ids": []}
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="repositories",
        )
        msg = mock_ws.send_json.call_args[0][0]
        assert "repositories" in msg["message"]


class TestNoDocsLoaded:
    @pytest.mark.asyncio
    async def test_no_docs_sends_error(self, mock_ws: AsyncMock, mock_state: MagicMock) -> None:
        mock_state.ananta.storage.list_documents.return_value = []
        data: dict[str, object] = {"question": "hi", "document_ids": ["empty-proj"]}
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
        )
        # First call is error (no status sent since we fail before query)
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "no documents" in msg["message"].lower()


class TestAllowBackgroundKnowledge:
    @pytest.mark.asyncio
    async def test_multi_query_passes_allow_background_knowledge(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        """Multi-project query passes allow_background_knowledge to engine."""
        data: dict[str, object] = {
            "question": "hi",
            "document_ids": ["proj1"],
            "allow_background_knowledge": True,
        }
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
        )
        engine = mock_state.ananta.get_project.return_value.rlm_engine
        call_kwargs = engine.query.call_args
        assert call_kwargs.kwargs.get("allow_background_knowledge") is True

    @pytest.mark.asyncio
    async def test_multi_query_defaults_allow_background_knowledge_false(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        """Multi-project query defaults allow_background_knowledge to False."""
        data: dict[str, object] = {
            "question": "hi",
            "document_ids": ["proj1"],
        }
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
        )
        engine = mock_state.ananta.get_project.return_value.rlm_engine
        call_kwargs = engine.query.call_args
        assert call_kwargs.kwargs.get("allow_background_knowledge") is False


class TestTopicResolution:
    @pytest.mark.asyncio
    async def test_invalid_topic_sends_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        def bad_session(state: object, topic: str) -> None:
            raise ValueError(f"Topic not found: {topic}")

        data: dict[str, object] = {
            "question": "hi",
            "document_ids": ["proj1"],
            "topic": "nonexistent",
        }
        await handle_multi_project_query(
            mock_ws,
            data,
            mock_state,
            threading.Event(),
            item_noun="documents",
            get_session=bad_session,
        )
        # Should have sent error about topic
        calls = mock_ws.send_json.call_args_list
        error_calls = [c for c in calls if c[0][0].get("type") == "error"]
        assert len(error_calls) == 1
        assert "topic" in error_calls[0][0][0]["message"].lower()
