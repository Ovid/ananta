"""FastAPI application for Shesha arXiv web interface.

Uses the shared app factory for boilerplate (lifespan, CORS, ``.well-known``
catch-all, WebSocket endpoint, static file mounting) and registers
arxiv-specific routes (papers, search) on a local router.

Generic routes (topic CRUD, traces, history/export, model, context-budget)
are provided by the shared ``create_shared_router()`` via callbacks that
adapt the arxiv ``AppState`` to the generic interface.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import arxiv
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse

from shesha.experimental.arxiv.download import to_parsed_document
from shesha.experimental.shared.app_factory import create_app
from shesha.experimental.shared.routes import (
    _resolve_topic_or_404,
    create_shared_router,
)
from shesha.experimental.shared.schemas import TopicInfo
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.schemas import (
    PaperAdd,
    PaperInfo,
    SearchResult,
)
from shesha.experimental.web.session import WebConversationSession
from shesha.experimental.web.websockets import websocket_handler


def _build_arxiv_topic_info(state: AppState) -> list[TopicInfo]:
    """Build topic listing for arxiv explorer (paper count per topic)."""
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


def _get_arxiv_session(state: AppState, topic_name: str) -> WebConversationSession:
    """Return the arxiv-flavoured session for a topic."""
    project_id = _resolve_topic_or_404(state, topic_name)
    project_dir = state.topic_mgr._storage._project_path(project_id)
    return WebConversationSession(project_dir)


def _create_arxiv_router(state: AppState) -> APIRouter:
    """Build the arxiv-specific API router.

    Contains paper management and search routes.  Topic CRUD, traces,
    history/export, model management, and context-budget routes are
    provided by the shared router.
    """
    router = APIRouter()

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

    Arxiv-specific routes (papers, search) are registered via a local
    ``APIRouter``.  Generic routes (topic CRUD, traces, history/export,
    model, context-budget) come from the shared router via callbacks.
    """
    arxiv_router = _create_arxiv_router(state)
    shared_router = create_shared_router(
        state,
        get_session=lambda s, name: _get_arxiv_session(state, name),
        build_topic_info=lambda s: _build_arxiv_topic_info(state),
        include_topic_crud=True,
        include_per_topic_history=True,
        include_context_budget=True,
    )

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
        extra_routers=[arxiv_router, shared_router],
    )
