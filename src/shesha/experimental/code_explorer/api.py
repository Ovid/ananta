"""Code explorer API.

Provides repo management routes (list, add, get, delete, check/apply updates)
and analysis routes for the code explorer web interface.  Uses the shared
``create_app()`` factory from ``shesha.experimental.shared.app_factory`` for
FastAPI boilerplate, then adds code-explorer-specific repo routes via an extra
router.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import litellm
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from shesha.exceptions import ProjectNotFoundError, RepoIngestError
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.schemas import (
    AnalysisResponse,
    ContextBudget,
    ModelInfo,
    ModelUpdate,
    RepoAdd,
    RepoInfo,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
    UpdateStatus,
)
from shesha.experimental.code_explorer.websockets import websocket_handler
from shesha.experimental.shared.app_factory import create_app
from shesha.models import RepoProjectResult


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


def _resolve_project_ids(state: CodeExplorerState, topic_name: str) -> list[str]:
    """Resolve a topic name to a list of project_ids.

    Falls back to all projects if the topic has no repos or doesn't exist.
    """
    try:
        repos = state.topic_mgr.list_repos(topic_name)
        if repos:
            return repos
    except ValueError:
        pass
    return state.shesha.list_projects()


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
        doc_count = len(state.shesha._storage.list_documents(pid))
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
        uncategorized = state.topic_mgr.list_uncategorized_repos(all_ids)
        return [_build_repo_info(pid) for pid in uncategorized]

    @router.post("/repos")
    def add_repo(body: RepoAdd) -> dict[str, object]:
        try:
            repo_result = state.shesha.create_project_from_repo(body.url)
        except RepoIngestError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
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
            return _build_repo_info(project_id)
        except ProjectNotFoundError:
            raise HTTPException(404, f"Project '{project_id}' not found")

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
    # Topic CRUD
    # ------------------------------------------------------------------

    @router.get("/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        names = state.topic_mgr.list_topics()
        return [
            TopicInfo(
                name=n,
                document_count=len(state.topic_mgr.list_repos(n)),
                size="",
                project_id=f"topic:{n}",
            )
            for n in names
        ]

    @router.post("/topics", status_code=201)
    def create_topic(body: TopicCreate) -> dict[str, str]:
        state.topic_mgr.create(body.name)
        return {"name": body.name, "project_id": ""}

    @router.patch("/topics/{name}")
    def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
        try:
            state.topic_mgr.rename(name, body.new_name)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"name": body.new_name}

    @router.delete("/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            state.topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"status": "deleted", "name": name}

    # ------------------------------------------------------------------
    # Topic-repo reference routes
    # ------------------------------------------------------------------

    @router.get("/topics/{name}/repos")
    def list_topic_repos(name: str) -> list[RepoInfo]:
        try:
            repo_ids = state.topic_mgr.list_repos(name)
        except ValueError:
            raise HTTPException(404, f"Topic '{name}' not found")
        return [_build_repo_info(pid) for pid in repo_ids]

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
    # Per-topic history (delegates to global session)
    # ------------------------------------------------------------------

    @router.get("/topics/{name}/history")
    def get_topic_history(name: str) -> dict[str, list[dict[str, object]]]:
        return {"exchanges": state.session.list_exchanges()}

    @router.delete("/topics/{name}/history")
    def clear_topic_history(name: str) -> dict[str, str]:
        state.session.clear()
        return {"status": "cleared"}

    @router.get("/topics/{name}/export", response_class=PlainTextResponse)
    def export_topic_transcript(name: str) -> PlainTextResponse:
        return PlainTextResponse(
            content=state.session.format_transcript(),
            media_type="text/markdown",
        )

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    @router.get("/topics/{name}/traces", response_model=list[TraceListItem])
    def list_traces(name: str) -> list[TraceListItem]:
        # Traces are stored per-project (repo), not per-topic.
        # Collect traces from all repos in the topic, or all repos if no topic.
        project_ids = _resolve_project_ids(state, name)
        items: list[TraceListItem] = []
        for pid in project_ids:
            trace_files = state.shesha._storage.list_traces(pid)
            for tf in trace_files:
                parsed = _parse_trace_file(tf)
                header = parsed["header"]
                summary = parsed["summary"]
                assert isinstance(header, dict)
                assert isinstance(summary, dict)
                total_tokens_raw = summary.get("total_tokens", {})
                assert isinstance(total_tokens_raw, dict)
                items.append(
                    TraceListItem(
                        trace_id=tf.stem,
                        question=str(header.get("question", "")),
                        timestamp=str(header.get("timestamp", "")),
                        status=str(summary.get("status", "unknown")),
                        total_tokens=sum(total_tokens_raw.values()),
                        duration_ms=int(summary.get("total_duration_ms", 0)),
                    )
                )
        return items

    @router.get("/topics/{name}/traces/{trace_id:path}", response_model=TraceFull)
    def get_trace(name: str, trace_id: str) -> TraceFull:
        project_ids = _resolve_project_ids(state, name)
        for pid in project_ids:
            trace_files = state.shesha._storage.list_traces(pid)
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

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    @router.get("/model", response_model=ModelInfo)
    def get_model() -> ModelInfo:
        max_input: int | None = None
        try:
            info = litellm.get_model_info(state.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=state.model, max_input_tokens=max_input)

    @router.put("/model", response_model=ModelInfo)
    def update_model(body: ModelUpdate) -> ModelInfo:
        state.model = body.model
        max_input: int | None = None
        try:
            info = litellm.get_model_info(body.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=body.model, max_input_tokens=max_input)

    # ------------------------------------------------------------------
    # Context budget
    # ------------------------------------------------------------------

    @router.get("/topics/{name}/context-budget", response_model=ContextBudget)
    def get_context_budget(name: str) -> ContextBudget:
        base_prompt_tokens = 2000
        history_chars = state.session.context_chars()
        used_tokens = base_prompt_tokens + (history_chars // 4)

        max_tokens = 128000
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
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    return create_app(
        state,
        title="Shesha Code Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[repo_router],
    )
