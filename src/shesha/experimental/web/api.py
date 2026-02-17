"""FastAPI application for Shesha arXiv web interface.

Uses the shared app factory for boilerplate (lifespan, CORS, ``.well-known``
catch-all, WebSocket endpoint, static file mounting) and registers
arxiv-specific routes (topics, papers, search) plus generic routes (traces,
history, model, context-budget) on a local router.

The shared ``create_shared_router()`` is *not* used directly because the arxiv
explorer has several incompatibilities: history is stored in
``_conversation.json`` (not ``conversation.json``), and the topic manager
does not expose ``resolve_all()``.  These routes are therefore kept here with
identical logic to the shared versions.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import arxiv
import litellm
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

from shesha.experimental.arxiv.download import to_parsed_document
from shesha.experimental.shared.app_factory import create_app
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.schemas import (
    ContextBudget,
    ConversationHistory,
    ModelInfo,
    ModelUpdate,
    PaperAdd,
    PaperInfo,
    SearchResult,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)
from shesha.experimental.web.session import WebConversationSession
from shesha.experimental.web.websockets import websocket_handler


def _resolve_topic_or_404(state: AppState, name: str) -> str:
    """Resolve a topic name to project_id, or raise 404."""
    project_id = state.topic_mgr.resolve(name)
    if not project_id:
        raise HTTPException(404, f"Topic '{name}' not found")
    return project_id


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


def _create_arxiv_router(state: AppState) -> APIRouter:
    """Build the arxiv-specific API router.

    Contains topic CRUD, paper management, search, traces, history/export,
    model management, and context-budget routes.
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

    # --- Papers ---

    @router.get("/api/topics/{name}/papers", response_model=list[PaperInfo])
    def list_papers(name: str) -> list[PaperInfo]:
        project_id = _resolve_topic_or_404(state, name)
        doc_names = state.topic_mgr._storage.list_documents(project_id)
        papers: list[PaperInfo] = []
        for doc_name in doc_names:
            meta = state.cache.get_meta(doc_name)
            if meta is not None:
                papers.append(
                    PaperInfo(
                        arxiv_id=meta.arxiv_id,
                        title=meta.title,
                        authors=meta.authors,
                        abstract=meta.abstract,
                        category=meta.primary_category,
                        date=meta.published.strftime("%Y-%m-%d"),
                        arxiv_url=meta.arxiv_url,
                        source_type=meta.source_type,
                    )
                )
        return papers

    @router.post("/api/papers/add", response_model=None)
    def add_paper(body: PaperAdd) -> dict[str, object] | JSONResponse:
        # Resolve all topic names to project IDs first
        topic_projects: list[tuple[str, str]] = []
        for topic_name in body.topics:
            project_id = state.topic_mgr.resolve(topic_name)
            if not project_id:
                raise HTTPException(404, f"Topic '{topic_name}' not found")
            topic_projects.append((topic_name, project_id))

        if state.cache.has(body.arxiv_id):
            # Already cached — copy into all topics immediately
            doc = to_parsed_document(body.arxiv_id, state.cache)
            for _, project_id in topic_projects:
                state.topic_mgr._storage.store_document(project_id, doc)
            return {"status": "added", "arxiv_id": body.arxiv_id}

        # Need to download — create background task
        task_id = str(uuid.uuid4())
        state.download_tasks[task_id] = {
            "papers": [{"arxiv_id": body.arxiv_id, "status": "pending"}],
        }

        def _download() -> None:
            # Import here to avoid circular import at module level — the
            # download module imports from the cache module which may
            # trigger lazy initialization.
            from shesha.experimental.arxiv.download import download_paper

            task = state.download_tasks[task_id]
            papers_list = task["papers"]
            assert isinstance(papers_list, list)
            papers_list[0]["status"] = "downloading"
            try:
                meta = state.searcher.get_by_id(body.arxiv_id)
                if meta is None:
                    papers_list[0]["status"] = "error"
                    return
                download_paper(meta, state.cache)
                doc = to_parsed_document(body.arxiv_id, state.cache)
                for _, project_id in topic_projects:
                    state.topic_mgr._storage.store_document(project_id, doc)
                papers_list[0]["status"] = "complete"
            except Exception:
                papers_list[0]["status"] = "error"

        thread = threading.Thread(target=_download, daemon=True)
        thread.start()

        return JSONResponse(status_code=202, content={"task_id": task_id})

    @router.delete("/api/topics/{name}/papers/{arxiv_id}")
    def remove_paper(name: str, arxiv_id: str) -> dict[str, str]:
        project_id = _resolve_topic_or_404(state, name)
        state.topic_mgr._storage.delete_document(project_id, arxiv_id)
        return {"status": "removed", "arxiv_id": arxiv_id}

    @router.get("/api/papers/tasks/{task_id}")
    def download_task_status(task_id: str) -> dict[str, object]:
        if task_id not in state.download_tasks:
            raise HTTPException(404, "Task not found")
        task = state.download_tasks[task_id]
        return {"task_id": task_id, "papers": task["papers"]}

    # --- Search ---

    @router.get("/api/search", response_model=list[SearchResult])
    def search_arxiv(
        q: str,
        author: str | None = None,
        category: str | None = None,
        sort_by: str = "relevance",
        start: int = 0,
    ) -> list[SearchResult]:
        try:
            results = state.searcher.search(
                q, author=author, category=category, sort_by=sort_by, start=start
            )
        except (arxiv.HTTPError, ValueError) as exc:
            raise HTTPException(502, f"arXiv API error: {exc}") from exc
        # Build a mapping of arxiv_id -> list of topic names
        topic_docs: dict[str, list[str]] = {}
        for topic in state.topic_mgr.list_topics():
            docs = state.topic_mgr._storage.list_documents(topic.project_id)
            for doc_name in docs:
                topic_docs.setdefault(doc_name, []).append(topic.name)

        return [
            SearchResult(
                arxiv_id=r.arxiv_id,
                title=r.title,
                authors=r.authors,
                abstract=r.abstract,
                category=r.primary_category,
                date=r.published.strftime("%Y-%m-%d"),
                arxiv_url=r.arxiv_url,
                in_topics=topic_docs.get(r.arxiv_id, []),
            )
            for r in results
        ]

    @router.get("/api/papers/search", response_model=list[SearchResult])
    def search_local(q: str) -> list[SearchResult]:
        q_lower = q.lower()

        # Build doc -> topics mapping across all topics
        topic_docs: dict[str, list[str]] = {}
        for topic in state.topic_mgr.list_topics():
            docs = state.topic_mgr._storage.list_documents(topic.project_id)
            for doc_name in docs:
                topic_docs.setdefault(doc_name, []).append(topic.name)

        results: list[SearchResult] = []
        for doc_name in topic_docs:
            meta = state.cache.get_meta(doc_name)
            if meta is None:
                continue
            title_match = q_lower in meta.title.lower()
            author_match = any(q_lower in a.lower() for a in meta.authors)
            id_match = q_lower in meta.arxiv_id.lower()
            if title_match or author_match or id_match:
                results.append(
                    SearchResult(
                        arxiv_id=meta.arxiv_id,
                        title=meta.title,
                        authors=meta.authors,
                        abstract=meta.abstract,
                        category=meta.primary_category,
                        date=meta.published.strftime("%Y-%m-%d"),
                        arxiv_url=meta.arxiv_url,
                        in_topics=topic_docs.get(doc_name, []),
                    )
                )

        return results

    # --- Traces ---

    @router.get("/api/topics/{name}/traces", response_model=list[TraceListItem])
    def list_traces(name: str) -> list[TraceListItem]:
        project_id = _resolve_topic_or_404(state, name)
        trace_files = state.topic_mgr._storage.list_traces(project_id)
        items: list[TraceListItem] = []
        for tf in trace_files:
            parsed = _parse_trace_file(tf)
            header = parsed["header"]
            summary = parsed["summary"]
            assert isinstance(header, dict)
            assert isinstance(summary, dict)
            total_tokens_raw = summary.get("total_tokens", {})
            assert isinstance(total_tokens_raw, dict)
            total_tokens = sum(total_tokens_raw.values())
            # Use filename stem as trace_id — matches what ws.py stores
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
        return items

    @router.get("/api/topics/{name}/traces/{trace_id:path}", response_model=TraceFull)
    def get_trace(name: str, trace_id: str) -> TraceFull:
        project_id = _resolve_topic_or_404(state, name)
        trace_files = state.topic_mgr._storage.list_traces(project_id)
        for tf in trace_files:
            # Match on filename stem (what ws.py stores) or header UUID
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

    # --- History & Export ---

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

    # --- Context Budget ---

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


def _make_ws_handler(state: AppState) -> Callable[[WebSocket], Awaitable[None]]:
    """Create a WebSocket handler bound to *state*.

    Returns an ``async (WebSocket) -> None`` callable suitable for the
    shared app factory's ``ws_handler`` parameter.
    """

    async def _handler(ws: WebSocket) -> None:
        await websocket_handler(ws, state)

    return _handler


def create_api(state: AppState) -> FastAPI:
    """Create and configure the FastAPI app using the shared factory.

    The shared ``create_app()`` provides: lifespan (starts/stops Shesha
    container pool), CORS middleware, ``.well-known`` catch-all, optional
    WebSocket endpoint, and static file mounting.

    Arxiv-specific routes are registered via a local ``APIRouter`` passed
    as an extra router to the factory.
    """
    # Wrap shesha.stop() to also close the arxiv searcher on shutdown.
    original_stop = state.shesha.stop

    def _stop_with_searcher() -> None:
        original_stop()
        state.searcher.close()

    state.shesha.stop = _stop_with_searcher  # type: ignore[method-assign]

    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    frontend_dist = Path(__file__).parent / "frontend" / "dist"

    return create_app(
        state,
        title="Shesha arXiv Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=_make_ws_handler(state),
        extra_routers=[_create_arxiv_router(state)],
    )
