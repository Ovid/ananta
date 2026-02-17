"""Code explorer WebSocket handler.

Delegates generic query/cancel dispatch to the shared WebSocket handler and
provides a custom query handler for cross-project queries.

Unlike the arxiv explorer (which maps topic -> single project, with
document_ids being document names within that project), the code explorer
treats ``document_ids`` as **project_ids** -- each maps to a whole repo.
Queries span multiple projects and use a global session for history.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi import WebSocket

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.shared.websockets import websocket_handler as shared_ws_handler
from shesha.models import ParsedDocument
from shesha.rlm.trace import StepType, TokenUsage

logger = logging.getLogger(__name__)


async def websocket_handler(ws: WebSocket, state: CodeExplorerState) -> None:
    """Handle WebSocket connections for the code explorer.

    Wraps the shared handler with a custom query handler that supports
    cross-project queries (document_ids are project_ids).
    """
    await shared_ws_handler(ws, state, query_handler=_handle_query)


async def _handle_query(
    ws: WebSocket,
    data: dict[str, Any],
    state: Any,
    cancel_event: threading.Event,
) -> None:
    """Execute a cross-project query."""
    question = str(data.get("question", ""))
    document_ids = data.get("document_ids")  # These are project_ids

    if not document_ids or not isinstance(document_ids, list) or len(document_ids) == 0:
        await ws.send_json(
            {
                "type": "error",
                "message": "Please select one or more repositories before querying",
            }
        )
        return

    # Load documents from all requested projects
    loaded_docs: list[ParsedDocument] = []
    storage = state.shesha._storage
    for project_id in document_ids:
        project_id_str = str(project_id)
        try:
            doc_names = storage.list_documents(project_id_str)
            for doc_name in doc_names:
                doc = storage.get_document(project_id_str, doc_name)
                loaded_docs.append(doc)
        except Exception:
            logger.warning("Could not load documents from project %s", project_id_str)

    if not loaded_docs:
        await ws.send_json(
            {"type": "error", "message": "No documents found in selected repositories"}
        )
        return

    # Build context from per-project analysis
    context_parts: list[str] = []
    for project_id in document_ids:
        try:
            analysis = state.shesha.get_analysis(str(project_id))
        except ProjectNotFoundError:
            logger.warning("Project %s not found, skipping analysis", project_id)
            continue
        if analysis is not None:
            context_parts.append(f"--- Analysis for {project_id} ---\n{analysis.overview}")

    # Build full question with history and context
    history_prefix = state.session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question
    if context_parts:
        full_question += "\n\n" + "\n\n".join(context_parts)

    # Use asyncio.Queue for thread-safe message passing from the query
    # thread to the async WebSocket send loop.
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(
        step_type: StepType,
        iteration: int,
        content: str,
        token_usage: TokenUsage,
    ) -> None:
        step_msg: dict[str, object] = {
            "type": "step",
            "step_type": step_type.value,
            "iteration": iteration,
            "content": content,
        }
        if token_usage.prompt_tokens > 0:
            step_msg["prompt_tokens"] = token_usage.prompt_tokens
            step_msg["completion_tokens"] = token_usage.completion_tokens
        loop.call_soon_threadsafe(message_queue.put_nowait, step_msg)

    await ws.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    # Drain the queue in a background task
    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Pick the first project's RLM engine (they share the same engine)
    first_project_id = str(document_ids[0])
    try:
        project = state.shesha.get_project(first_project_id)
    except ProjectNotFoundError:
        await ws.send_json({"type": "error", "message": f"Repository {first_project_id} not found"})
        await message_queue.put(None)
        await drain_task
        return
    rlm_engine = project._rlm_engine
    if rlm_engine is None:
        await ws.send_json({"type": "error", "message": "Query engine not configured"})
        await message_queue.put(None)
        await drain_task
        return

    try:
        result = await loop.run_in_executor(
            None,
            lambda: rlm_engine.query(
                documents=[d.content for d in loaded_docs],
                question=full_question,
                doc_names=[d.name for d in loaded_docs],
                on_progress=on_progress,
                storage=storage,
                project_id=first_project_id,
                cancel_event=cancel_event,
            ),
        )
    except Exception as exc:
        await message_queue.put(None)
        await drain_task
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Signal the drain task to stop, then wait for it
    await message_queue.put(None)
    await drain_task

    # Get trace_id
    trace_id = None
    traces = storage.list_traces(first_project_id)
    if traces:
        trace_id = traces[-1].stem

    consulted_ids = [str(pid) for pid in document_ids]
    document_bytes = sum(len(d.content.encode("utf-8")) for d in loaded_docs)

    # Save to global session
    state.session.add_exchange(
        question=question,
        answer=result.answer,
        trace_id=trace_id,
        tokens={
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        execution_time=result.execution_time,
        model=state.model,
        document_ids=consulted_ids,
    )

    await ws.send_json(
        {
            "type": "complete",
            "answer": result.answer,
            "trace_id": trace_id,
            "tokens": {
                "prompt": result.token_usage.prompt_tokens,
                "completion": result.token_usage.completion_tokens,
                "total": result.token_usage.total_tokens,
            },
            "duration_ms": int(result.execution_time * 1000),
            "document_ids": consulted_ids,
            "document_bytes": document_bytes,
        }
    )
