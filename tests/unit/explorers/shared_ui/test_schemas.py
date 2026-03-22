"""Tests for shared generic Pydantic schemas."""

from ananta.explorers.shared_ui.schemas import (
    ContextBudget,
    ConversationHistory,
    ExchangeSchema,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)


def test_topic_create():
    t = TopicCreate(name="Abiogenesis")
    assert t.name == "Abiogenesis"


def test_topic_rename():
    t = TopicRename(new_name="Origins of Life")
    assert t.new_name == "Origins of Life"


def test_topic_info():
    t = TopicInfo(
        name="Abiogenesis",
        document_count=5,
        size="2.3 MB",
        project_id="2026-02-12-abiogenesis",
    )
    assert t.name == "Abiogenesis"
    assert t.document_count == 5
    assert t.size == "2.3 MB"
    assert t.project_id == "2026-02-12-abiogenesis"


def test_trace_step_schema_all_fields():
    s = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="print('hello')",
        timestamp="2025-01-15T10:30:01Z",
        tokens_used=150,
        duration_ms=320,
    )
    assert s.step_type == "code_generated"
    assert s.iteration == 1
    assert s.content == "print('hello')"
    assert s.timestamp == "2025-01-15T10:30:01Z"
    assert s.tokens_used == 150
    assert s.duration_ms == 320


def test_trace_step_schema_optional_defaults():
    s = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="print('hello')",
        timestamp="2025-01-15T10:30:01Z",
    )
    assert s.tokens_used is None
    assert s.duration_ms is None


def test_trace_list_item():
    t = TraceListItem(
        trace_id="trace-abc",
        question="What is life?",
        timestamp="2025-01-15T10:30:00Z",
        status="completed",
        total_tokens=500,
        duration_ms=12000,
    )
    assert t.trace_id == "trace-abc"
    assert t.question == "What is life?"
    assert t.status == "completed"
    assert t.total_tokens == 500
    assert t.duration_ms == 12000


def test_trace_full():
    step = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="x = 1",
        timestamp="2025-01-15T10:30:01Z",
    )
    t = TraceFull(
        trace_id="trace-abc",
        question="What is life?",
        model="gpt-5-mini",
        timestamp="2025-01-15T10:30:00Z",
        steps=[step],
        total_tokens={"prompt": 100, "completion": 50, "total": 150},
        total_iterations=1,
        duration_ms=12000,
        status="completed",
    )
    assert t.trace_id == "trace-abc"
    assert t.model == "gpt-5-mini"
    assert len(t.steps) == 1
    assert t.document_ids == []


def test_trace_full_with_document_ids():
    t = TraceFull(
        trace_id="trace-abc",
        question="What is life?",
        model="gpt-5-mini",
        timestamp="2025-01-15T10:30:00Z",
        steps=[],
        total_tokens={"prompt": 100, "completion": 50},
        total_iterations=0,
        duration_ms=0,
        status="completed",
        document_ids=["doc-1", "doc-2"],
    )
    assert t.document_ids == ["doc-1", "doc-2"]


def test_exchange_schema_uses_document_ids():
    """ExchangeSchema in shared module uses document_ids (not paper_ids)."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        trace_id="2025-01-15T10-30-00-123_abc",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
        document_ids=["doc-1", "doc-2"],
    )
    assert e.document_ids == ["doc-1", "doc-2"]
    assert e.exchange_id == "uuid-1"
    assert e.question == "What?"
    assert e.answer == "This."
    assert e.trace_id == "2025-01-15T10-30-00-123_abc"


def test_exchange_schema_document_ids_default():
    """document_ids defaults to None when not provided."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    assert e.document_ids is None
    assert e.trace_id is None


def test_conversation_history():
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    h = ConversationHistory(exchanges=[e])
    assert len(h.exchanges) == 1
    assert h.exchanges[0].exchange_id == "uuid-1"


def test_conversation_history_empty():
    h = ConversationHistory(exchanges=[])
    assert h.exchanges == []


def test_model_info():
    m = ModelInfo(model="gpt-5-mini", max_input_tokens=128000)
    assert m.model == "gpt-5-mini"
    assert m.max_input_tokens == 128000


def test_model_info_optional_max_tokens():
    m = ModelInfo(model="gpt-5-mini")
    assert m.max_input_tokens is None


def test_model_update():
    m = ModelUpdate(model="gpt-5")
    assert m.model == "gpt-5"


def test_exchange_schema_gave_up_default():
    """gave_up defaults to False when not provided."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    assert e.gave_up is False


def test_exchange_schema_gave_up_true():
    """gave_up=True is stored and serialized."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="Partial findings here.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
        gave_up=True,
    )
    assert e.gave_up is True
    d = e.model_dump()
    assert d["gave_up"] is True


def test_context_budget():
    b = ContextBudget(
        used_tokens=31000,
        max_tokens=73000,
        percentage=42.5,
        level="green",
    )
    assert b.used_tokens == 31000
    assert b.max_tokens == 73000
    assert b.percentage == 42.5
    assert b.level == "green"
