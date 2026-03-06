"""Document explorer WebSocket handler.

Thin wrapper around the shared multi-project WebSocket handler.
Builds context from upload metadata (filename, content_type) and
delegates to :func:`handle_multi_project_query`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from shesha.experimental.shared.websockets import (
    handle_multi_project_query,
    websocket_handler as shared_ws_handler,
)

logger = logging.getLogger(__name__)


async def _build_doc_context(state: Any, project_ids: list[str]) -> str:
    """Build context from upload metadata (filename, content_type)."""
    parts: list[str] = []
    for pid in project_ids:
        meta_path = state.uploads_dir / pid / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                filename = meta.get("filename", pid)
                content_type = meta.get("content_type", "unknown")
                parts.append(f"--- Document: {filename} (type: {content_type}) ---")
            except (OSError, json.JSONDecodeError):
                logger.debug("Skipping unreadable metadata for %s", pid, exc_info=True)
    return "\n\n".join(parts)


async def _handle_query(
    ws: WebSocket, data: dict[str, Any], state: Any, cancel_event: Any
) -> None:
    """Execute a cross-project query against uploaded documents."""
    await handle_multi_project_query(
        ws,
        data,
        state,
        cancel_event,
        item_noun="documents",
        build_context=_build_doc_context,
        get_session=get_topic_session,
    )


async def websocket_handler(ws: WebSocket, state: DocumentExplorerState) -> None:
    """Handle WebSocket connections for the document explorer."""
    await shared_ws_handler(ws, state, query_handler=_handle_query)
