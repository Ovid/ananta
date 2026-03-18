"""Generic API routes shared across Shesha experimental tools.

Provides ``create_shared_router()`` which returns a FastAPI ``APIRouter``
containing topic CRUD, trace listing/retrieval, model management, and
optional per-topic history/export and context-budget routes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from shesha.experimental.shared.schemas import (
    ContextBudget,
    ConversationHistory,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)
from shesha.experimental.shared.session import WebConversationSession
from shesha.experimental.shared.topics import BaseTopicManager

# Type aliases for callbacks
GetSession = Callable[[Any, str], WebConversationSession]
BuildTopicInfo = Callable[[Any], list[TopicInfo]]
ResolveProjectIds = Callable[[Any, str], list[str]]
ListTraceFiles = Callable[[Any, str], list[Path]]


def _topic_error_to_status(e: ValueError) -> int:
    """Map a topic manager ValueError to an HTTP status code."""
    msg = str(e)
    if "already exists" in msg and "slug" not in msg:
        return 409
    if "not found" in msg.lower():
        return 404
    return 422


def create_item_router(topic_mgr: BaseTopicManager) -> APIRouter:
    """Create an APIRouter with topic CRUD and item reference routes."""
    router = APIRouter(prefix="/api")

    @router.get("/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        names = topic_mgr.list_topics()
        return [
            TopicInfo(
                name=n,
                document_count=len(topic_mgr.list_items(n)),
                size="",
                project_id=f"topic:{n}",
            )
            for n in names
        ]

    @router.post("/topics", status_code=201)
    def create_topic(body: TopicCreate) -> dict[str, str]:
        try:
            topic_mgr.create(body.name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"name": body.name, "project_id": f"topic:{body.name}"}

    @router.patch("/topics/{name}")
    def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
        try:
            topic_mgr.rename(name, body.new_name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"name": body.new_name}

    @router.delete("/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"status": "deleted", "name": name}

    @router.post("/topics/{name}/items/{project_id}")
    def add_item_to_topic(name: str, project_id: str) -> dict[str, str]:
        try:
            topic_mgr.create(name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        topic_mgr.add_item(name, project_id)
        return {"status": "added", "topic": name, "project_id": project_id}

    @router.delete("/topics/{name}/items/{project_id}")
    def remove_item_from_topic(name: str, project_id: str) -> dict[str, str]:
        try:
            topic_mgr.remove_item(name, project_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"status": "removed", "topic": name, "project_id": project_id}

    return router


def resolve_topic_or_404(state: Any, name: str) -> str:
    """Resolve a topic name to project_id, or raise 404."""
    project_id = state.topic_mgr.resolve(name)
    if not project_id:
        raise HTTPException(404, f"Topic '{name}' not found")
    return str(project_id)


def _resolve_all_project_ids(state: Any, name: str) -> list[str]:
    """Resolve a topic to all project_ids it references.

    Falls back to a single-element list when the topic manager does not
    support ``resolve_all`` (i.e. single-repo topics).
    """
    resolve_all = getattr(state.topic_mgr, "resolve_all", None)
    if resolve_all is not None:
        ids: list[str] = resolve_all(name)
        if ids:
            return ids
    # Fallback: single project
    project_id = resolve_topic_or_404(state, name)
    return [project_id]


def _parse_trace_file(trace_file: Path) -> dict[str, object]:
    """Parse a JSONL trace file into header, steps, and summary."""
    header: dict[str, object] = {}
    steps: list[dict[str, object]] = []
    summary: dict[str, object] = {}
    for line in trace_file.read_text().strip().splitlines():
        record = json.loads(line)
        rtype = record.get("type")
        if rtype == "header":
            header = record
        elif rtype == "step":
            steps.append(record)
        elif rtype == "summary":
            summary = record
    return {"header": header, "steps": steps, "summary": summary}


def create_shared_router(
    state: Any,
    *,
    get_session: GetSession | None = None,
    build_topic_info: BuildTopicInfo | None = None,
    resolve_project_ids: ResolveProjectIds | None = None,
    list_trace_files: ListTraceFiles | None = None,
    include_topic_crud: bool = True,
    include_per_topic_history: bool = True,
    include_context_budget: bool = True,
) -> APIRouter:
    """Create an APIRouter with generic routes.

    Parameters
    ----------
    state:
        Application state.  Must expose ``model`` (str) and ``topic_mgr``
        with the following interface:

        * ``resolve(name) -> str | None`` — required by default session
          creation and trace resolution when *get_session* and
          *resolve_project_ids* are not provided.  Also required when
          *include_topic_crud* is True (used to check for duplicates
          in the create-topic route).  Not needed when all three
          callbacks are provided and *include_topic_crud* is False.
        * ``list_topics()``, ``create(name)``, ``rename(old, new)``,
          ``delete(name)`` — required when *include_topic_crud* is True
          and *build_topic_info* is not provided (for ``list_topics``).
        * ``resolve_all(name) -> list[str]`` — optional; used by
          default trace resolution.  Falls back to ``resolve()`` when
          absent.  Bypassed by *resolve_project_ids*.
        * ``_storage._project_path(project_id) -> Path`` — used to
          create default sessions.  Bypassed by *get_session*.
        * ``_storage.list_traces(project_id) -> list[Path]`` — used to
          locate trace files.  Bypassed by *list_trace_files*.
    get_session:
        Optional callback ``(state, topic_name) -> WebConversationSession``.
        When provided, overrides the default per-project session creation
        for history, export, and context-budget routes.
    build_topic_info:
        Optional callback ``(state) -> list[TopicInfo]``.
        When provided, overrides the default topic listing logic.
    resolve_project_ids:
        Optional callback ``(state, topic_name) -> list[str]``.
        When provided, overrides the default project ID resolution
        for trace routes.
    list_trace_files:
        Optional callback ``(state, project_id) -> list[Path]``.
        When provided, overrides the default
        ``state.topic_mgr._storage.list_traces(project_id)`` call
        for trace routes.  Useful when trace files are stored in a
        different storage backend (e.g. ``state.shesha._storage``).
    include_topic_crud:
        When ``True`` (default), register topic CRUD routes (list, create,
        rename, delete).
    include_per_topic_history:
        When ``True`` (default), register per-topic history, clear-history,
        and export routes.
    include_context_budget:
        When ``True`` (default), register the context-budget route.
    """
    router = APIRouter()

    # --- Internal helpers ---

    def _get_session_for_topic(topic_name: str) -> WebConversationSession:
        """Get the session for a topic, using callback or default."""
        if get_session is not None:
            return get_session(state, topic_name)
        project_id = resolve_topic_or_404(state, topic_name)
        project_dir = state.topic_mgr._storage._project_path(project_id)
        return WebConversationSession(project_dir)

    def _get_project_ids(name: str) -> list[str]:
        """Resolve project IDs for a topic, using callback or default."""
        if resolve_project_ids is not None:
            return resolve_project_ids(state, name)
        return _resolve_all_project_ids(state, name)

    def _get_trace_files(project_id: str) -> list[Path]:
        """Get trace files for a project, using callback or default."""
        if list_trace_files is not None:
            return list_trace_files(state, project_id)
        return state.topic_mgr._storage.list_traces(project_id)  # type: ignore[no-any-return]

    # --- Topics ---

    if include_topic_crud:

        @router.get("/api/topics", response_model=list[TopicInfo])
        def list_topics() -> list[TopicInfo]:
            if build_topic_info is not None:
                return build_topic_info(state)
            topics = state.topic_mgr.list_topics()
            return [
                TopicInfo(
                    name=t.name,
                    document_count=t.document_count,
                    size=t.formatted_size,
                    project_id=t.project_id,
                )
                for t in topics
            ]

        @router.post("/api/topics", status_code=201)
        def create_topic(body: TopicCreate) -> dict[str, str]:
            existing = state.topic_mgr.resolve(body.name)
            if existing:
                raise HTTPException(409, f"Topic '{body.name}' already exists")
            project_id = state.topic_mgr.create(body.name)
            return {"name": body.name, "project_id": project_id}

        @router.patch("/api/topics/{name}")
        def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
            try:
                state.topic_mgr.rename(name, body.new_name)
            except ValueError as e:
                raise HTTPException(404, str(e)) from e
            return {"name": body.new_name}

        @router.delete("/api/topics/{name}")
        def delete_topic(name: str) -> dict[str, str]:
            try:
                state.topic_mgr.delete(name)
            except ValueError as e:
                raise HTTPException(404, str(e)) from e
            return {"status": "deleted", "name": name}

    # --- Traces ---

    @router.get("/api/topics/{name}/traces", response_model=list[TraceListItem])
    def list_traces(name: str) -> list[TraceListItem]:
        project_ids = _get_project_ids(name)
        items: list[TraceListItem] = []
        for project_id in project_ids:
            trace_files = _get_trace_files(project_id)
            for tf in trace_files:
                parsed = _parse_trace_file(tf)
                header = parsed["header"]
                summary = parsed["summary"]
                assert isinstance(header, dict)
                assert isinstance(summary, dict)
                total_tokens_raw = summary.get("total_tokens", {})
                assert isinstance(total_tokens_raw, dict)
                total_tokens = sum(total_tokens_raw.values())
                items.append(
                    TraceListItem(
                        trace_id=tf.stem,
                        question=str(header.get("question", "")),
                        timestamp=str(header.get("timestamp", "")),
                        status=str(summary.get("status", "unknown")),
                        total_tokens=total_tokens,
                        duration_ms=int(summary.get("total_duration_ms", 0)),
                    )
                )
        # Sort by timestamp for consistent ordering across projects
        items.sort(key=lambda item: item.timestamp)
        return items

    def _find_trace_file(
        name: str, trace_id: str
    ) -> tuple[Path, dict[str, object]]:
        """Find a trace file by topic name and trace ID.

        Returns the file path and parsed contents, or raises 404.
        """
        project_ids = _get_project_ids(name)
        for project_id in project_ids:
            trace_files = _get_trace_files(project_id)
            for tf in trace_files:
                parsed = _parse_trace_file(tf)
                header = parsed["header"]
                assert isinstance(header, dict)
                if tf.stem == trace_id or header.get("trace_id") == trace_id:
                    return tf, parsed
        raise HTTPException(404, f"Trace '{trace_id}' not found")

    @router.get("/api/topics/{name}/traces/{trace_id:path}", response_model=TraceFull)
    def get_trace(name: str, trace_id: str) -> TraceFull:
        _tf, parsed = _find_trace_file(name, trace_id)
        header = parsed["header"]
        summary = parsed["summary"]
        steps_raw = parsed["steps"]
        assert isinstance(header, dict)
        assert isinstance(summary, dict)
        assert isinstance(steps_raw, list)
        total_tokens_raw = summary.get("total_tokens", {})
        assert isinstance(total_tokens_raw, dict)
        steps = [
            TraceStepSchema(
                step_type=str(s.get("step_type", "")),
                iteration=int(s.get("iteration", 0)),
                content=str(s.get("content", "")),
                timestamp=str(s.get("timestamp", "")),
                tokens_used=s.get("tokens_used"),
                duration_ms=s.get("duration_ms"),
            )
            for s in steps_raw
        ]
        doc_ids_raw = header.get("document_ids", [])
        doc_ids = list(doc_ids_raw) if isinstance(doc_ids_raw, list) else []
        return TraceFull(
            trace_id=trace_id,
            question=str(header.get("question", "")),
            model=str(header.get("model", "")),
            timestamp=str(header.get("timestamp", "")),
            steps=steps,
            total_tokens=total_tokens_raw,
            total_iterations=int(summary.get("total_iterations", 0)),
            duration_ms=int(summary.get("total_duration_ms", 0)),
            status=str(summary.get("status", "unknown")),
            document_ids=doc_ids,
        )

    # --- Trace Download ---

    @router.get("/api/topics/{name}/trace-download/{trace_id}")
    def download_trace(name: str, trace_id: str) -> FileResponse:
        tf, _parsed = _find_trace_file(name, trace_id)
        return FileResponse(
            tf,
            filename=tf.name,
            media_type="application/x-ndjson",
        )

    # --- History & Export (optional) ---

    if include_per_topic_history:

        @router.get("/api/topics/{name}/history", response_model=ConversationHistory)
        def get_history(name: str) -> ConversationHistory:
            session = _get_session_for_topic(name)
            return ConversationHistory(exchanges=session.list_exchanges())  # type: ignore[arg-type]

        @router.delete("/api/topics/{name}/history")
        def clear_history(name: str) -> dict[str, str]:
            session = _get_session_for_topic(name)
            session.clear()
            return {"status": "cleared"}

        @router.get("/api/topics/{name}/export", response_class=PlainTextResponse)
        def export_transcript(name: str) -> PlainTextResponse:
            session = _get_session_for_topic(name)
            content = session.format_transcript()
            return PlainTextResponse(content=content, media_type="text/markdown")

    # --- Model ---

    @router.get("/api/model", response_model=ModelInfo)
    def get_model() -> ModelInfo:
        max_input: int | None = None
        try:
            info = litellm.get_model_info(state.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=state.model, max_input_tokens=max_input)

    @router.put("/api/model", response_model=ModelInfo)
    def update_model(body: ModelUpdate) -> ModelInfo:
        state.model = body.model
        max_input: int | None = None
        try:
            info = litellm.get_model_info(body.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=body.model, max_input_tokens=max_input)

    # --- Context Budget (optional) ---

    if include_context_budget:

        @router.get("/api/topics/{name}/context-budget", response_model=ContextBudget)
        def get_context_budget(name: str) -> ContextBudget:
            # Documents go to the Docker sandbox, not the LLM context.
            # The LLM context contains: system prompt (~2k tokens) +
            # conversation history prefix + iterative code/output messages.
            # We estimate: base overhead + history chars.
            base_prompt_tokens = 2000  # system prompt + context metadata

            session = _get_session_for_topic(name)
            history_chars = session.context_chars()

            # ~4 chars per token heuristic
            used_tokens = base_prompt_tokens + (history_chars // 4)

            # Get max tokens from litellm
            max_tokens = 128000  # reasonable default
            try:
                info = litellm.get_model_info(state.model)
                max_input = info.get("max_input_tokens")
                if max_input is not None:
                    max_tokens = max_input
            except Exception:
                pass  # Fall back to default
            percentage = (used_tokens / max_tokens) * 100
            if percentage < 50:
                level = "green"
            elif percentage < 80:
                level = "amber"
            else:
                level = "red"

            return ContextBudget(
                used_tokens=used_tokens,
                max_tokens=max_tokens,
                percentage=round(percentage, 1),
                level=level,
            )

    return router
