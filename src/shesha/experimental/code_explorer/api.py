"""Code explorer API.

Provides repo management routes (list, add, get, delete, check/apply updates)
and analysis routes for the code explorer web interface.  Uses the shared
``create_app()`` factory from ``shesha.experimental.shared.app_factory`` for
FastAPI boilerplate, then adds code-explorer-specific repo routes via an extra
router.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.schemas import (
    AnalysisResponse,
    RepoAdd,
    RepoInfo,
    UpdateStatus,
)
from shesha.experimental.code_explorer.websockets import websocket_handler
from shesha.experimental.shared.app_factory import create_app
from shesha.models import RepoProjectResult


def _create_repo_router(state: CodeExplorerState) -> APIRouter:
    """Create API router for repo management routes."""
    router = APIRouter(prefix="/api")

    # Cache of pending update results keyed by project_id, so that
    # apply-updates can call the stored apply_updates() method.
    pending_updates: dict[str, RepoProjectResult] = {}

    @router.get("/repos")
    def list_repos() -> list[RepoInfo]:
        project_ids = state.shesha.list_projects()
        result: list[RepoInfo] = []
        for pid in project_ids:
            info = state.shesha.get_project_info(pid)
            # TODO: Replace with a public Shesha API method when available
            doc_count = len(state.shesha._storage.list_documents(pid))
            result.append(
                RepoInfo(
                    project_id=pid,
                    source_url=info.source_url or "",
                    file_count=doc_count,
                    analysis_status=info.analysis_status,
                )
            )
        return result

    @router.post("/repos")
    def add_repo(body: RepoAdd) -> dict[str, object]:
        repo_result = state.shesha.create_project_from_repo(body.url)
        project_id = repo_result.project.project_id

        if body.topic:
            state.topic_mgr.create(body.topic)
            state.topic_mgr.add_repo(body.topic, project_id)

        return {
            "project_id": project_id,
            "status": repo_result.status,
            "files_ingested": repo_result.files_ingested,
        }

    @router.get("/repos/{project_id}")
    def get_repo(project_id: str) -> RepoInfo:
        try:
            info = state.shesha.get_project_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")
        # TODO: Replace with a public Shesha API method when available
        doc_count = len(state.shesha._storage.list_documents(project_id))
        return RepoInfo(
            project_id=project_id,
            source_url=info.source_url or "",
            file_count=doc_count,
            analysis_status=info.analysis_status,
        )

    @router.delete("/repos/{project_id}")
    def delete_repo(project_id: str) -> dict[str, str]:
        try:
            state.shesha.get_project_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")
        state.topic_mgr.remove_repo_from_all(project_id)
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

        repo_result = state.shesha.create_project_from_repo(source_url)

        # Cache the result if updates are available so apply-updates can use it
        if repo_result.status == "updates_available":
            pending_updates[project_id] = repo_result

        return UpdateStatus(
            status=repo_result.status,
            files_ingested=repo_result.files_ingested,
        )

    @router.post("/repos/{project_id}/apply-updates")
    def apply_updates(project_id: str) -> UpdateStatus:
        if project_id not in pending_updates:
            raise HTTPException(409, f"No pending update for project '{project_id}'")

        repo_result = pending_updates.pop(project_id)
        updated = repo_result.apply_updates()

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

    # ------------------------------------------------------------------
    # Topic-repo reference routes
    # ------------------------------------------------------------------

    @router.post("/topics/{name}/repos/{project_id}")
    def add_repo_to_topic(name: str, project_id: str) -> dict[str, str]:
        state.topic_mgr.create(name)
        state.topic_mgr.add_repo(name, project_id)
        return {"status": "added", "topic": name, "project_id": project_id}

    @router.delete("/topics/{name}/repos/{project_id}")
    def remove_repo_from_topic(name: str, project_id: str) -> dict[str, str]:
        try:
            state.topic_mgr.remove_repo(name, project_id)
        except ValueError:
            raise HTTPException(404, f"Repo '{project_id}' not found in topic '{name}'")
        return {"status": "removed", "topic": name, "project_id": project_id}

    # ------------------------------------------------------------------
    # Global history routes
    # ------------------------------------------------------------------

    @router.get("/history")
    def get_history() -> dict[str, list[dict[str, object]]]:
        return {"exchanges": state.session.list_exchanges()}

    @router.delete("/history")
    def clear_history() -> dict[str, str]:
        state.session.clear()
        return {"status": "cleared"}

    @router.get("/export", response_class=PlainTextResponse)
    def export_transcript() -> PlainTextResponse:
        return PlainTextResponse(
            content=state.session.format_transcript(),
            media_type="text/markdown",
        )

    return router


def create_api(state: CodeExplorerState) -> FastAPI:
    """Create the code explorer FastAPI application."""
    repo_router = _create_repo_router(state)
    return create_app(
        state,
        title="Shesha Code Explorer",
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[repo_router],
    )
