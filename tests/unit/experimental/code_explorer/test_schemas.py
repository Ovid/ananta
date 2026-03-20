"""Tests for code explorer Pydantic schemas."""

from __future__ import annotations

import pydantic
import pytest

from ananta.experimental.code_explorer.schemas import (
    AnalysisResponse,
    ContextBudget,
    ExchangeSchema,
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

# ---------------------------------------------------------------------------
# RepoAdd
# ---------------------------------------------------------------------------


def test_repo_add_minimal():
    r = RepoAdd(url="https://github.com/org/repo")
    assert r.url == "https://github.com/org/repo"
    assert r.topic is None


def test_repo_add_with_topic():
    r = RepoAdd(url="https://github.com/org/repo", topic="my-topic")
    assert r.topic == "my-topic"


def test_repo_add_requires_url():
    with pytest.raises(pydantic.ValidationError):
        RepoAdd()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RepoInfo
# ---------------------------------------------------------------------------


def test_repo_info_all_fields():
    r = RepoInfo(
        project_id="2026-02-14-my-repo",
        source_url="https://github.com/org/repo",
        file_count=42,
        analysis_status="current",
    )
    assert r.project_id == "2026-02-14-my-repo"
    assert r.source_url == "https://github.com/org/repo"
    assert r.file_count == 42
    assert r.analysis_status == "current"


def test_repo_info_analysis_status_nullable():
    r = RepoInfo(
        project_id="proj-1",
        source_url="https://github.com/org/repo",
        file_count=10,
        analysis_status=None,
    )
    assert r.analysis_status is None


def test_repo_info_requires_all_fields():
    with pytest.raises(pydantic.ValidationError):
        RepoInfo(project_id="proj-1")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AnalysisResponse
# ---------------------------------------------------------------------------


def test_analysis_response_all_fields():
    a = AnalysisResponse(
        version="1.0",
        generated_at="2026-02-14T12:00:00Z",
        head_sha="abc123def456",
        overview="A web framework for building APIs.",
        components=[
            {"name": "router", "description": "URL routing"},
            {"name": "middleware", "description": "Request pipeline"},
        ],
        external_dependencies=[
            {"name": "pydantic", "version": "2.x"},
        ],
        caveats="Analysis covers only Python files.",
    )
    assert a.version == "1.0"
    assert a.generated_at == "2026-02-14T12:00:00Z"
    assert a.head_sha == "abc123def456"
    assert a.overview == "A web framework for building APIs."
    assert len(a.components) == 2
    assert a.components[0]["name"] == "router"
    assert len(a.external_dependencies) == 1
    assert a.caveats == "Analysis covers only Python files."


def test_analysis_response_empty_lists():
    a = AnalysisResponse(
        version="1.0",
        generated_at="2026-02-14T12:00:00Z",
        head_sha="abc123",
        overview="Empty project.",
        components=[],
        external_dependencies=[],
        caveats="",
    )
    assert a.components == []
    assert a.external_dependencies == []


def test_analysis_response_requires_all_fields():
    with pytest.raises(pydantic.ValidationError):
        AnalysisResponse(version="1.0")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# UpdateStatus
# ---------------------------------------------------------------------------


def test_update_status():
    u = UpdateStatus(status="unchanged", files_ingested=0)
    assert u.status == "unchanged"
    assert u.files_ingested == 0


def test_update_status_with_updates():
    u = UpdateStatus(status="updates_available", files_ingested=15)
    assert u.status == "updates_available"
    assert u.files_ingested == 15


def test_update_status_requires_all_fields():
    with pytest.raises(pydantic.ValidationError):
        UpdateStatus(status="unchanged")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Re-exported shared schemas are importable from code_explorer.schemas
# ---------------------------------------------------------------------------


def test_reexported_topic_create():
    t = TopicCreate(name="my-project")
    assert t.name == "my-project"


def test_reexported_topic_rename():
    t = TopicRename(new_name="renamed-project")
    assert t.new_name == "renamed-project"


def test_reexported_topic_info():
    """Code explorer uses the shared TopicInfo with document_count."""
    t = TopicInfo(
        name="my-project",
        document_count=10,
        size="1.5 MB",
        project_id="2026-02-14-my-project",
    )
    assert t.document_count == 10
    assert t.name == "my-project"


def test_reexported_exchange_schema():
    """Code explorer uses the shared ExchangeSchema with document_ids."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What does main.py do?",
        answer="It starts the server.",
        timestamp="2026-02-14T12:00:00Z",
        tokens={"prompt": 200, "completion": 100, "total": 300},
        execution_time=10.5,
        model="gpt-5-mini",
        document_ids=["repo-1"],
    )
    assert e.document_ids == ["repo-1"]


def test_reexported_model_info():
    m = ModelInfo(model="gpt-5-mini", max_input_tokens=128000)
    assert m.model == "gpt-5-mini"


def test_reexported_model_update():
    m = ModelUpdate(model="gpt-5")
    assert m.model == "gpt-5"


def test_reexported_context_budget():
    b = ContextBudget(
        used_tokens=10000,
        max_tokens=73000,
        percentage=13.7,
        level="green",
    )
    assert b.level == "green"


def test_reexported_trace_list_item():
    t = TraceListItem(
        trace_id="trace-1",
        question="What?",
        timestamp="2026-02-14T12:00:00Z",
        status="completed",
        total_tokens=500,
        duration_ms=3000,
    )
    assert t.trace_id == "trace-1"


def test_reexported_trace_full():
    step = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="x = 1",
        timestamp="2026-02-14T12:00:01Z",
    )
    t = TraceFull(
        trace_id="trace-1",
        question="What?",
        model="gpt-5-mini",
        timestamp="2026-02-14T12:00:00Z",
        steps=[step],
        total_tokens={"prompt": 100, "completion": 50},
        total_iterations=1,
        duration_ms=3000,
        status="completed",
        document_ids=["repo-1"],
    )
    assert t.document_ids == ["repo-1"]
    assert len(t.steps) == 1


def test_reexported_trace_step_schema():
    s = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="print('hello')",
        timestamp="2026-02-14T12:00:01Z",
        tokens_used=150,
        duration_ms=320,
    )
    assert s.step_type == "code_generated"
    assert s.tokens_used == 150
