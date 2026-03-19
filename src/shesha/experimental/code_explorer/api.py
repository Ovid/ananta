"""Code explorer API.

Provides repo management routes (list, add, get, delete, check/apply updates)
and analysis routes for the code explorer web interface.  Uses the shared
``create_app()`` factory from ``shesha.experimental.shared.app_factory`` for
FastAPI boilerplate and the shared router from
``shesha.experimental.shared.routes`` for traces, model, history, and
context-budget routes.  Code-explorer-specific repo and topic CRUD routes
live on a local router.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException

from shesha.exceptions import ProjectNotFoundError, RepoIngestError
from shesha.experimental.code_explorer.dependencies import (
    CodeExplorerState,
    get_topic_session,
)
from shesha.experimental.code_explorer.schemas import (
    AnalysisResponse,
    RepoAdd,
    RepoInfo,
    UpdateStatus,
)
from shesha.experimental.code_explorer.websockets import websocket_handler
from shesha.experimental.shared.app_factory import create_app
from shesha.experimental.shared.routes import create_item_router, create_shared_router
from shesha.models import RepoProjectResult


import re as _re


def _sanitize_ingest_error(exc: RepoIngestError) -> str:
    """Return user-safe error message with internal filesystem paths stripped."""
    msg = str(exc)
    # Strip quoted or unquoted absolute paths (e.g. '/var/lib/shesha/repos/...')
    msg = _re.sub(r"'/?(?:[\w./-]+/){2,}[\w.-]+'", "'<path>'", msg)
    msg = _re.sub(r"(?<!\w)/?(?:[\w./-]+/){2,}[\w.-]+", "<path>", msg)
    return msg


def _resolve_code_project_ids(state: CodeExplorerState, topic_name: str) -> list[str]:
    """Resolve a topic name to project IDs for trace aggregation.

    Falls back to all projects if the topic has no repos or doesn't exist.
    """
    try:
        items = state.topic_mgr.list_items(topic_name)
        if items:
            return items
    except ValueError:
        pass  # Topic doesn't exist; fall back to all projects
    return state.shesha.list_projects()


def _list_code_trace_files(state: CodeExplorerState, project_id: str) -> list[Path]:
    """List trace files from Shesha storage (not topic manager storage)."""
    return state.shesha.storage.list_traces(project_id)


def _create_repo_router(state: CodeExplorerState) -> APIRouter:
    """Create API router for repo management routes."""
    router = APIRouter(prefix="/api")

    # Cache of pending update results keyed by project_id, so that
    # apply-updates can call the stored apply_updates() method.
    pending_updates: dict[str, RepoProjectResult] = {}

    def _build_repo_info(pid: str) -> RepoInfo:
        """Build a RepoInfo for a project_id."""
        info = state.shesha.get_project_info(pid)
        # TODO: Replace with a public Shesha API method when available
        doc_count = len(state.shesha.storage.list_documents(pid))
        return RepoInfo(
            project_id=pid,
            source_url=info.source_url or "",
            file_count=doc_count,
            analysis_status=info.analysis_status,
        )

    @router.get("/repos")
    def list_repos() -> list[RepoInfo]:
        project_ids = state.shesha.list_projects()
        return [_build_repo_info(pid) for pid in project_ids]

    @router.get("/repos/uncategorized")
    def list_uncategorized_repos() -> list[RepoInfo]:
        all_ids = state.shesha.list_projects()
        uncategorized = state.topic_mgr.list_uncategorized(all_ids)
        return [_build_repo_info(pid) for pid in uncategorized]

    @router.get("/topics/{name}/items")
    def list_topic_items(name: str) -> list[RepoInfo]:
        try:
            repo_ids = state.topic_mgr.list_items(name)
        except ValueError as e:
            raise HTTPException(404, f"Topic '{name}' not found") from e
        return [_build_repo_info(pid) for pid in repo_ids]

    @router.post("/repos")
    def add_repo(body: RepoAdd) -> dict[str, object]:
        try:
            repo_result = state.shesha.create_project_from_repo(body.url)
        except RepoIngestError as exc:
            raise HTTPException(422, detail=_sanitize_ingest_error(exc)) from exc
        project_id = repo_result.project.project_id

        if body.topic:
            try:
                state.topic_mgr.create(body.topic)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            state.topic_mgr.add_item(body.topic, project_id)

        return {
            "project_id": project_id,
            "status": repo_result.status,
            "files_ingested": repo_result.files_ingested,
        }

    @router.get("/repos/{project_id}")
    def get_repo(project_id: str) -> RepoInfo:
        try:
            return _build_repo_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")

    @router.delete("/repos/{project_id}")
    def delete_repo(project_id: str) -> dict[str, str]:
        try:
            state.shesha.get_project_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")
        state.topic_mgr.remove_item_from_all(project_id)
        state.shesha.delete_project(project_id, cleanup_repo=True)
        return {"status": "deleted", "project_id": project_id}

    @router.post("/repos/{project_id}/check-updates")
    def check_updates(project_id: str) -> UpdateStatus:
        try:
            info = state.shesha.get_project_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")

        source_url = info.source_url
        if not source_url:
            raise HTTPException(400, f"Project '{project_id}' has no source URL")

        try:
            repo_result = state.shesha.create_project_from_repo(source_url, name=project_id)
        except RepoIngestError as exc:
            raise HTTPException(422, detail=_sanitize_ingest_error(exc)) from exc

        # Cache the result if updates are available so apply-updates can use it
        if repo_result.status == "updates_available":
            pending_updates[project_id] = repo_result

        return UpdateStatus(
            status=repo_result.status,
            files_ingested=repo_result.files_ingested,
        )

    @router.post("/repos/{project_id}/apply-updates")
    def apply_updates(project_id: str) -> UpdateStatus:
        repo_result = pending_updates.pop(project_id, None)
        if repo_result is not None:
            pass  # Use cached result from check-updates
        else:
            # Self-heal: re-derive update state when cache is empty
            # (e.g., after server restart between check and apply).
            try:
                info = state.shesha.get_project_info(project_id)
            except ProjectNotFoundError:
                raise HTTPException(404, f"Project '{project_id}' not found")

            source_url = info.source_url
            if not source_url:
                raise HTTPException(400, f"Project '{project_id}' has no source URL")

            try:
                repo_result = state.shesha.create_project_from_repo(source_url, name=project_id)
            except RepoIngestError as exc:
                raise HTTPException(422, detail=_sanitize_ingest_error(exc)) from exc

            if repo_result.status != "updates_available":
                raise HTTPException(409, f"No updates available for project '{project_id}'")

        try:
            updated = repo_result.apply_updates()
        except RepoIngestError as exc:
            raise HTTPException(422, detail=_sanitize_ingest_error(exc)) from exc

        return UpdateStatus(
            status=updated.status,
            files_ingested=updated.files_ingested,
        )

    @router.post("/repos/{project_id}/analyze")
    def generate_analysis(project_id: str) -> AnalysisResponse:
        try:
            analysis = state.shesha.generate_analysis(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")
        return AnalysisResponse(**asdict(analysis))

    @router.get("/repos/{project_id}/analysis")
    def get_analysis(project_id: str) -> AnalysisResponse:
        try:
            analysis = state.shesha.get_analysis(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")
        if analysis is None:
            raise HTTPException(404, f"No analysis exists for project '{project_id}'")
        return AnalysisResponse(**asdict(analysis))

    return router


def create_api(state: CodeExplorerState) -> FastAPI:
    """Create the code explorer FastAPI application."""
    repo_router = _create_repo_router(state)
    item_router = create_item_router(state.topic_mgr)
    shared_router = create_shared_router(
        state,
        get_session=lambda s, name: get_topic_session(s, name),
        resolve_project_ids=lambda s, name: _resolve_code_project_ids(s, name),
        list_trace_files=lambda s, pid: _list_code_trace_files(s, pid),
        include_topic_crud=False,
        include_per_topic_history=True,
        include_context_budget=True,
    )
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    return create_app(
        state,
        title="Shesha Code Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[repo_router, item_router, shared_router],
    )
