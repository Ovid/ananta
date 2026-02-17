"""Generic WebSocket handler for query execution.

Provides a reusable WebSocket handler that dispatches ``query`` and
``cancel`` messages.  Apps can extend it by passing *extra_handlers*
(e.g. for citation checking), a *build_context* callback, or a fully
custom *query_handler* (e.g. for cross-project queries).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from shesha.exceptions import DocumentNotFoundError
from shesha.experimental.shared.session import WebConversationSession
from shesha.models import ParsedDocument
from shesha.rlm.trace import StepType, TokenUsage

logger = logging.getLogger(__name__)

# Type alias for extra handler callables.
# Signature: async def handler(ws, data, state) -> None
ExtraHandler = Callable[[WebSocket, dict[str, object], Any], Any]

# Type alias for the build_context callback.
# Signature: def build_context(document_ids, state, loaded_docs) -> str
BuildContext = Callable[[list[str], Any, list[ParsedDocument]], str]

# Type alias for session factory.
# Signature: def factory(project_dir: Path) -> WebConversationSession
SessionFactory = Callable[..., WebConversationSession]

# Type alias for the query handler callback.
# Signature: async def handler(ws, data, state, cancel_event) -> None
QueryHandler = Callable[
    [WebSocket, dict[str, object], Any, threading.Event],
    Coroutine[Any, Any, None],
]


async def websocket_handler(
    websocket: WebSocket,
    state: Any,
    *,
    query_handler: QueryHandler | None = None,
    extra_handlers: dict[str, ExtraHandler] | None = None,
    build_context: BuildContext | None = None,
    session_factory: SessionFactory | None = None,
) -> None:
    """Handle WebSocket connections for queries and cancellation.

    Parameters
    ----------
    websocket:
        The FastAPI WebSocket connection.
    state:
        Application state (must expose ``topic_mgr``, ``shesha``, ``model``).
    query_handler:
        Optional async callback ``(ws, data, state, cancel_event) -> None``
        that executes a query.  When not provided, the built-in topic-based
        handler is used (configured via *build_context* / *session_factory*).
    extra_handlers:
        Mapping of message type -> async handler for app-specific messages.
    build_context:
        Optional callback that returns extra context to append to the user
        question (e.g. citation instructions, cross-repo context).
    session_factory:
        Callable that creates a session given a project directory Path.
        Defaults to the shared ``WebConversationSession``.  The arXiv app
        passes its own subclass so history uses ``_conversation.json``.
    """
    if query_handler is not None:
        actual_handler = query_handler
    else:

        async def actual_handler(
            ws: WebSocket,
            data: dict[str, object],
            st: Any,
            cancel_event: threading.Event,
        ) -> None:
            await _handle_query(
                ws,
                data,
                st,
                cancel_event,
                build_context=build_context,
                session_factory=session_factory,
            )

    await websocket.accept()
    cancel_event: threading.Event | None = None
    query_task: asyncio.Task[None] | None = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "cancel":
                if cancel_event is not None:
                    cancel_event.set()
                await websocket.send_json({"type": "cancelled"})

            elif msg_type == "query":
                # Cancel and await any in-flight query before starting a new one
                if cancel_event is not None:
                    cancel_event.set()
                if query_task is not None and not query_task.done():
                    query_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await query_task
                cancel_event = threading.Event()
                query_task = asyncio.create_task(
                    actual_handler(websocket, data, state, cancel_event)
                )

            elif extra_handlers and msg_type in extra_handlers:
                await extra_handlers[msg_type](websocket, data, state)

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )
    except WebSocketDisconnect:
        if cancel_event is not None:
            cancel_event.set()
        if query_task is not None and not query_task.done():
            query_task.cancel()


async def _handle_query(
    websocket: WebSocket,
    data: dict[str, object],
    state: Any,
    cancel_event: threading.Event,
    *,
    build_context: BuildContext | None = None,
    session_factory: SessionFactory | None = None,
) -> None:
    """Execute a query and stream progress via the WebSocket."""
    topic = str(data.get("topic", ""))
    question = str(data.get("question", ""))

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await websocket.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    doc_names = state.topic_mgr._storage.list_documents(project_id)
    if not doc_names:
        await websocket.send_json({"type": "error", "message": "No documents in topic"})
        return

    project = state.shesha.get_project(project_id)

    # Load documents filtered by document_ids (required)
    document_ids = data.get("document_ids")
    loaded_docs: list[ParsedDocument]

    if not document_ids or not isinstance(document_ids, list) or len(document_ids) == 0:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Please select one or more documents before querying",
            }
        )
        return

    # Load only the requested documents, skipping any that don't exist
    loaded_docs = []
    for did in document_ids:
        try:
            doc = state.topic_mgr._storage.get_document(project_id, str(did))
            loaded_docs.append(doc)
        except DocumentNotFoundError:
            logger.warning("Requested document_id %r not found in project %s", did, project_id)
    if not loaded_docs:
        await websocket.send_json(
            {"type": "error", "message": "No valid documents found for the given document_ids"}
        )
        return

    # Load session for history prefix
    project_dir = state.topic_mgr._storage._project_path(project_id)
    factory = session_factory or WebConversationSession
    session = factory(project_dir)
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question

    # Append context from the build_context callback if provided
    if build_context is not None:
        context_suffix = build_context([d.name for d in loaded_docs], state, loaded_docs)
        full_question += context_suffix

    # Use asyncio.Queue for thread-safe message passing from the query
    # thread to the async WebSocket send loop.
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(
        step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
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

    await websocket.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    # Drain the queue in a background task
    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await websocket.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Run query in thread to avoid blocking the event loop.
    rlm_engine = project._rlm_engine
    if rlm_engine is None:
        await websocket.send_json({"type": "error", "message": "Query engine not configured"})
        await message_queue.put(None)
        await drain_task
        return

    storage = state.topic_mgr._storage
    try:
        result = await loop.run_in_executor(
            None,
            lambda: rlm_engine.query(
                documents=[d.content for d in loaded_docs],
                question=full_question,
                doc_names=[d.name for d in loaded_docs],
                on_progress=on_progress,
                storage=storage,
                project_id=project_id,
                cancel_event=cancel_event,
            ),
        )
    except Exception as exc:
        await message_queue.put(None)
        await drain_task
        await websocket.send_json({"type": "error", "message": str(exc)})
        return

    # Signal the drain task to stop, then wait for it
    await message_queue.put(None)
    await drain_task

    # Save to session
    trace_id = None
    traces = state.topic_mgr._storage.list_traces(project_id)
    if traces:
        trace_id = traces[-1].stem

    consulted_document_ids = [d.name for d in loaded_docs]
    document_bytes = sum(len(d.content.encode("utf-8")) for d in loaded_docs)

    session.add_exchange(
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
        document_ids=consulted_document_ids,
    )

    await websocket.send_json(
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
            "document_ids": consulted_document_ids,
            "document_bytes": document_bytes,
        }
    )
