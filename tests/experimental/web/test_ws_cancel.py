"""Tests for WebSocket cancel-during-query behavior."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from shesha.experimental.web.websockets import websocket_handler

# The web handler now delegates to the shared handler, so we patch the
# shared module's _handle_query.
_HANDLE_QUERY_PATCH = "shesha.experimental.shared.websockets._handle_query"


class TestCancelDuringQuery:
    """Cancel messages must be processed while a query is in-flight."""

    @pytest.mark.asyncio
    async def test_cancel_during_query_sends_cancelled_response(self) -> None:
        """A cancel message sent while a query runs should be acknowledged promptly."""
        query_started = asyncio.Event()

        async def blocking_query(
            ws: Any, data: Any, state: Any, cancel_event: Any, **kwargs: Any
        ) -> None:
            """Simulate a long-running query that yields to the event loop."""
            query_started.set()
            await asyncio.sleep(10)

        call_idx = 0

        async def mock_receive_json() -> dict[str, object]:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return {
                    "type": "query",
                    "topic": "t",
                    "question": "q",
                    "paper_ids": ["p"],
                }
            if call_idx == 2:
                await query_started.wait()
                return {"type": "cancel"}
            raise WebSocketDisconnect()

        ws = AsyncMock()
        ws.receive_json = mock_receive_json
        state = MagicMock()

        with patch(
            _HANDLE_QUERY_PATCH,
            side_effect=blocking_query,
        ):
            await asyncio.wait_for(websocket_handler(ws, state), timeout=3.0)

        cancelled_msgs = [
            c
            for c in ws.send_json.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("type") == "cancelled"
        ]
        assert len(cancelled_msgs) == 1

    @pytest.mark.asyncio
    async def test_cancel_sets_event_on_inflight_query(self) -> None:
        """The cancel_event passed to _handle_query should be set when cancel arrives."""
        query_started = asyncio.Event()
        captured_cancel_event: list[Any] = []

        async def blocking_query(
            ws: Any, data: Any, state: Any, cancel_event: Any, **kwargs: Any
        ) -> None:
            captured_cancel_event.append(cancel_event)
            query_started.set()
            # Block until cancelled or timeout
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: cancel_event.wait(timeout=5.0))

        call_idx = 0

        async def mock_receive_json() -> dict[str, object]:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return {
                    "type": "query",
                    "topic": "t",
                    "question": "q",
                    "paper_ids": ["p"],
                }
            if call_idx == 2:
                await query_started.wait()
                return {"type": "cancel"}
            raise WebSocketDisconnect()

        ws = AsyncMock()
        ws.receive_json = mock_receive_json
        state = MagicMock()

        with patch(
            _HANDLE_QUERY_PATCH,
            side_effect=blocking_query,
        ):
            await asyncio.wait_for(websocket_handler(ws, state), timeout=5.0)

        assert len(captured_cancel_event) == 1
        assert captured_cancel_event[0].is_set()

    @pytest.mark.asyncio
    async def test_new_query_cancels_previous(self) -> None:
        """Sending a second query should cancel the first one."""
        first_query_started = asyncio.Event()
        captured_events: list[Any] = []

        second_query_started = asyncio.Event()

        async def blocking_query(
            ws: Any, data: Any, state: Any, cancel_event: Any, **kwargs: Any
        ) -> None:
            captured_events.append(cancel_event)
            if len(captured_events) == 1:
                first_query_started.set()
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: cancel_event.wait(timeout=5.0))
            else:
                second_query_started.set()

        call_idx = 0

        async def mock_receive_json() -> dict[str, object]:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return {
                    "type": "query",
                    "topic": "t",
                    "question": "q1",
                    "paper_ids": ["p"],
                }
            if call_idx == 2:
                await first_query_started.wait()
                return {
                    "type": "query",
                    "topic": "t",
                    "question": "q2",
                    "paper_ids": ["p"],
                }
            # Let the second query task start before disconnecting
            await second_query_started.wait()
            raise WebSocketDisconnect()

        ws = AsyncMock()
        ws.receive_json = mock_receive_json
        state = MagicMock()

        with patch(
            _HANDLE_QUERY_PATCH,
            side_effect=blocking_query,
        ):
            await asyncio.wait_for(websocket_handler(ws, state), timeout=5.0)

        # First query's cancel_event should have been set
        assert len(captured_events) == 2
        assert captured_events[0].is_set()
