"""Code explorer WebSocket handler.

Thin wrapper around the shared multi-project WebSocket handler.
Builds context from per-project analysis overviews and delegates
to :func:`handle_multi_project_query`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

from ananta.exceptions import ProjectNotFoundError
from ananta.experimental.code_explorer.dependencies import (
    CodeExplorerState,
    get_topic_session,
)
from ananta.experimental.shared.websockets import (
    handle_multi_project_query,
)
from ananta.experimental.shared.websockets import (
    websocket_handler as shared_ws_handler,
)

logger = logging.getLogger(__name__)


async def _build_code_context(state: Any, project_ids: list[str]) -> str:
    """Build context from per-project analysis overviews."""
    parts: list[str] = []
    for pid in project_ids:
        try:
            analysis = state.ananta.get_analysis(pid)
        except ProjectNotFoundError:
            logger.warning("Project %s not found, skipping analysis", pid)
            continue
        if analysis is not None:
            parts.append(f"--- Analysis for {pid} ---\n{analysis.overview}")
    return "\n\n".join(parts)


async def _handle_query(ws: WebSocket, data: dict[str, Any], state: Any, cancel_event: Any) -> None:
    """Execute a cross-project query against code repositories."""
    await handle_multi_project_query(
        ws,
        data,
        state,
        cancel_event,
        item_noun="repositories",
        build_context=_build_code_context,
        get_session=get_topic_session,
    )


async def websocket_handler(ws: WebSocket, state: CodeExplorerState) -> None:
    """Handle WebSocket connections for the code explorer."""
    await shared_ws_handler(ws, state, query_handler=_handle_query)
