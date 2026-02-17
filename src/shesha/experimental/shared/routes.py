"""Generic API routes shared across Shesha experimental tools.

Provides ``create_shared_router()`` which returns a FastAPI ``APIRouter``
containing topic CRUD, trace listing/retrieval, model management, and
optional per-topic history/export and context-budget routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

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


def _resolve_topic_or_404(state: Any, name: str) -> str:
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
    project_id = _resolve_topic_or_404(state, name)
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
    include_per_topic_history: bool = True,
    include_context_budget: bool = True,
) -> APIRouter:
    """Create an APIRouter with generic routes.

    Parameters
    ----------
    state:
        Application state. Must expose ``topic_mgr``, ``model``.
    include_per_topic_history:
        When ``True`` (default), register per-topic history, clear-history,
        and export routes.
    include_context_budget:
        When ``True`` (default), register the context-budget route.
    """
    router = APIRouter()

    # --- Topics ---

    @router.get("/api/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        topics = state.topic_mgr.list_topics()
        return [
            TopicInfo(
                name=t.name,
                document_count=t.paper_count,
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
        project_ids = _resolve_all_project_ids(state, name)
        items: list[TraceListItem] = []
        for project_id in project_ids:
            trace_files = state.topic_mgr._storage.list_traces(project_id)
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

    @router.get("/api/topics/{name}/traces/{trace_id:path}", response_model=TraceFull)
    def get_trace(name: str, trace_id: str) -> TraceFull:
        project_ids = _resolve_all_project_ids(state, name)
        for project_id in project_ids:
            trace_files = state.topic_mgr._storage.list_traces(project_id)
            for tf in trace_files:
                parsed = _parse_trace_file(tf)
                header = parsed["header"]
                assert isinstance(header, dict)
                if tf.stem == trace_id or header.get("trace_id") == trace_id:
                    summary = parsed["summary"]
                    steps_raw = parsed["steps"]
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
        raise HTTPException(404, f"Trace '{trace_id}' not found")

    # --- History & Export (optional) ---

    if include_per_topic_history:

        @router.get("/api/topics/{name}/history", response_model=ConversationHistory)
        def get_history(name: str) -> ConversationHistory:
            project_id = _resolve_topic_or_404(state, name)
            project_dir = state.topic_mgr._storage._project_path(project_id)
            session = WebConversationSession(project_dir)
            return ConversationHistory(exchanges=session.list_exchanges())  # type: ignore[arg-type]

        @router.delete("/api/topics/{name}/history")
        def clear_history(name: str) -> dict[str, str]:
            project_id = _resolve_topic_or_404(state, name)
            project_dir = state.topic_mgr._storage._project_path(project_id)
            session = WebConversationSession(project_dir)
            session.clear()
            return {"status": "cleared"}

        @router.get("/api/topics/{name}/export", response_class=PlainTextResponse)
        def export_transcript(name: str) -> PlainTextResponse:
            project_id = _resolve_topic_or_404(state, name)
            project_dir = state.topic_mgr._storage._project_path(project_id)
            session = WebConversationSession(project_dir)
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
            project_id = _resolve_topic_or_404(state, name)
            project_dir = state.topic_mgr._storage._project_path(project_id)

            # Documents go to the Docker sandbox, not the LLM context.
            # The LLM context contains: system prompt (~2k tokens) +
            # conversation history prefix + iterative code/output messages.
            # We estimate: base overhead + history chars.
            base_prompt_tokens = 2000  # system prompt + context metadata

            session = WebConversationSession(project_dir)
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
