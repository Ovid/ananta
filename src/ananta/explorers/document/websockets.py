"""Document explorer WebSocket handler.

Thin wrapper around the shared multi-project WebSocket handler.
Builds context from upload metadata (filename, content_type) and
delegates to :func:`handle_multi_project_query`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import WebSocket

from ananta.explorers.document.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from ananta.explorers.shared_ui.websockets import (
    handle_multi_project_query,
)
from ananta.explorers.shared_ui.websockets import (
    websocket_handler as shared_ws_handler,
)

logger = logging.getLogger(__name__)

# Defense-in-depth scrubbing for the per-document context line (I5).
#
# The output of `_build_doc_context` is appended to `full_question` (the
# user-role message) without any boundary marker — so an unscrubbed
# attacker-controlled `meta["filename"]` could break out of the
# `--- Document: ... ---` line and inject content into the highest-trust
# position in the prompt. The upload + rename routes now reject filenames
# with control bytes / path separators / `..` (I5/I6 at the API layer),
# but legacy meta.json entries written before validation existed remain
# on disk indefinitely and must also be defended against.
#
# Scrub: replace any control byte (incl. newline / tab / CR / NUL / ESC)
# with a single space, and collapse runs of three-or-more dashes (the
# marker delimiter) to two dashes so an attacker can't synthesise a
# `--- ...` boundary inside the line.
_CONTROL_BYTES_RE = re.compile(r"[\x00-\x1f\x7f]")
_DASH_RUN_RE = re.compile(r"-{3,}")


def _scrub_for_context(value: str) -> str:
    """Sanitise an attacker-controlled string for inline prompt rendering."""
    return _DASH_RUN_RE.sub("--", _CONTROL_BYTES_RE.sub(" ", value))


async def _build_doc_context(state: Any, project_ids: list[str]) -> str:
    """Build context from upload metadata (filename, content_type)."""
    parts: list[str] = []
    for pid in project_ids:
        meta_path = state.uploads_dir / pid / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                filename = _scrub_for_context(str(meta.get("filename", pid)))
                content_type = _scrub_for_context(str(meta.get("content_type", "unknown")))
                parts.append(f"--- Document: {filename} (type: {content_type}) ---")
            except (OSError, json.JSONDecodeError):
                logger.debug("Skipping unreadable metadata for %s", pid, exc_info=True)
    return "\n\n".join(parts)


async def _handle_query(ws: WebSocket, data: dict[str, Any], state: Any, cancel_event: Any) -> None:
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
