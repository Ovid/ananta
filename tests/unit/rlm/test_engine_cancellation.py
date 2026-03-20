"""Tests for RLM engine cancellation."""

import inspect
import threading
from unittest.mock import MagicMock

from ananta.rlm.engine import RLMEngine


def test_query_accepts_cancel_event():
    """RLMEngine.query() accepts a cancel_event parameter."""
    sig = inspect.signature(RLMEngine.query)
    assert "cancel_event" in sig.parameters


def test_query_exits_when_cancel_event_set():
    """Query loop exits after current iteration when cancel_event is set."""
    event = threading.Event()

    # Mock the LLM to set the cancel event after first call
    mock_llm = MagicMock()
    call_count = 0

    def fake_complete(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            event.set()  # Cancel after first LLM call
        resp = MagicMock()
        resp.content = "I need to think more about this."
        resp.prompt_tokens = 100
        resp.completion_tokens = 50
        resp.total_tokens = 150
        return resp

    mock_llm.complete = fake_complete
    mock_factory = MagicMock(return_value=mock_llm)

    engine = RLMEngine(model="test-model", llm_client_factory=mock_factory)

    mock_executor = MagicMock()
    mock_executor.is_alive = True
    mock_executor.execute.return_value = MagicMock(
        status="ok",
        stdout="",
        stderr="",
        error=None,
        final_answer=None,
        final_var=None,
        final_value=None,
        vars=None,
    )

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_executor
    engine.set_pool(mock_pool)

    result = engine.query(
        documents=["test doc"],
        question="What is this?",
        cancel_event=event,
    )

    assert result.answer == "[interrupted]"
    # Should have only done 1 iteration, not max_iterations (20)
    assert call_count == 1


def test_query_returns_interrupted_status_in_trace():
    """Cancelled query writes trace with interrupted status."""
    event = threading.Event()
    event.set()  # Set immediately — should exit before first iteration

    mock_llm = MagicMock()
    mock_factory = MagicMock(return_value=mock_llm)

    engine = RLMEngine(model="test-model", llm_client_factory=mock_factory)

    mock_executor = MagicMock()
    mock_executor.is_alive = True
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_executor
    engine.set_pool(mock_pool)

    result = engine.query(
        documents=["test doc"],
        question="What is this?",
        cancel_event=event,
    )

    assert result.answer == "[interrupted]"
    # LLM should never have been called
    mock_llm.complete.assert_not_called()


def test_project_query_accepts_cancel_event():
    """Project.query() passes cancel_event to engine."""
    from ananta.project import Project

    mock_engine = MagicMock(spec=RLMEngine)
    mock_storage = MagicMock()
    mock_storage.load_all_documents.return_value = []

    project = Project(
        project_id="test",
        storage=mock_storage,
        parser_registry=MagicMock(),
        rlm_engine=mock_engine,
    )
    event = threading.Event()

    mock_engine.query.return_value = MagicMock()
    project.query("question", cancel_event=event)

    # Verify cancel_event was passed through
    _, kwargs = mock_engine.query.call_args
    assert kwargs["cancel_event"] is event
