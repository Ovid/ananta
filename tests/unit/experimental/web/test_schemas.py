"""Tests for web API schemas."""

from shesha.experimental.web.schemas import (
    ContextBudget,
    DownloadTaskStatus,
    ExchangeSchema,
    PaperAdd,
    SearchResult,
    TopicCreate,
    TopicInfo,
    TraceStepSchema,
)


def test_topic_create():
    t = TopicCreate(name="Abiogenesis")
    assert t.name == "Abiogenesis"


def test_topic_info():
    t = TopicInfo(
        name="Abiogenesis",
        document_count=5,
        size="2.3 MB",
        project_id="2026-02-12-abiogenesis",
    )
    assert t.document_count == 5


def test_paper_add_multi_topic():
    p = PaperAdd(arxiv_id="2501.08753", topics=["Chess", "Education"])
    assert len(p.topics) == 2


def test_search_result_includes_in_topics():
    r = SearchResult(
        arxiv_id="2501.08753",
        title="Test Paper",
        authors=["Author A"],
        abstract="Abstract text",
        category="q-bio.PE",
        date="2025-01-15",
        arxiv_url="https://arxiv.org/abs/2501.08753",
        in_topics=["Abiogenesis"],
    )
    assert r.in_topics == ["Abiogenesis"]


def test_trace_step_schema():
    s = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="print('hello')",
        timestamp="2025-01-15T10:30:01Z",
        tokens_used=150,
    )
    assert s.step_type == "code_generated"


def test_exchange_schema():
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        trace_id="2025-01-15T10-30-00-123_abc",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    assert e.trace_id is not None


def test_context_budget():
    b = ContextBudget(
        used_tokens=31000,
        max_tokens=73000,
        percentage=42.5,
        level="green",
    )
    assert b.level == "green"


def test_download_task_status():
    d = DownloadTaskStatus(
        task_id="abc123",
        papers=[
            {"arxiv_id": "2501.08753", "status": "downloading"},
        ],
    )
    assert d.task_id == "abc123"
