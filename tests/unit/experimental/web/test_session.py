"""Tests for persistent web conversation session."""

from pathlib import Path
from unittest.mock import patch

import pytest

from ananta.experimental.web.session import WebConversationSession


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "test-topic"


@pytest.fixture
def session(session_dir: Path) -> WebConversationSession:
    session_dir.mkdir(parents=True)
    return WebConversationSession(session_dir)


def test_empty_session_has_no_exchanges(session: WebConversationSession) -> None:
    assert session.list_exchanges() == []


def test_add_exchange(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What is this?",
        answer="A test.",
        trace_id="trace-123",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    exchanges = session.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "What is this?"
    assert exchanges[0]["trace_id"] == "trace-123"
    assert "exchange_id" in exchanges[0]
    assert "timestamp" in exchanges[0]


def test_persistence_across_instances(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    s1 = WebConversationSession(session_dir)
    s1.add_exchange(
        question="Q1",
        answer="A1",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )

    s2 = WebConversationSession(session_dir)
    exchanges = s2.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "Q1"


def test_clear_history(session: WebConversationSession) -> None:
    session.add_exchange(
        question="Q",
        answer="A",
        trace_id="t",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    session.clear()
    assert session.list_exchanges() == []


def test_format_history_prefix_empty(session: WebConversationSession) -> None:
    assert session.format_history_prefix() == ""


def test_format_history_prefix_with_exchanges(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What is X?",
        answer="X is Y.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    prefix = session.format_history_prefix()
    assert "Previous conversation:" in prefix
    assert "What is X?" in prefix
    assert "X is Y." in prefix


def test_format_transcript(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What?",
        answer="This.",
        trace_id="t1",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    transcript = session.format_transcript()
    assert "What?" in transcript
    assert "This." in transcript


def test_context_chars(session: WebConversationSession) -> None:
    """context_chars returns total character count of history."""
    assert session.context_chars() == 0
    session.add_exchange(
        question="Hello",
        answer="World",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert session.context_chars() > 0


def test_add_exchange_stores_document_ids(session: WebConversationSession) -> None:
    """add_exchange stores document_ids in the exchange when provided."""
    exchange = session.add_exchange(
        question="What?",
        answer="Something.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
        document_ids=["paper-a", "paper-c"],
    )
    assert exchange["document_ids"] == ["paper-a", "paper-c"]

    # Verify persistence
    reloaded = WebConversationSession(session._file.parent)
    assert reloaded.list_exchanges()[0]["document_ids"] == ["paper-a", "paper-c"]


def test_corrupt_json_loads_as_empty(session_dir: Path) -> None:
    """A corrupt conversation file should not crash; session loads as empty."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "_conversation.json").write_text("{bad json")
    s = WebConversationSession(session_dir)
    assert s.list_exchanges() == []


def test_save_is_atomic_on_crash(session_dir: Path) -> None:
    """If _save crashes mid-write, the original file is preserved."""
    session_dir.mkdir(parents=True, exist_ok=True)
    s = WebConversationSession(session_dir)
    s.add_exchange(
        question="Q1",
        answer="A1",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )

    conv_file = session_dir / "_conversation.json"
    original_data = conv_file.read_text()

    # Simulate a crash during the second save by making os.replace raise
    with patch("os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            s.add_exchange(
                question="Q2",
                answer="A2",
                trace_id="t2",
                tokens={"prompt": 10, "completion": 5, "total": 15},
                execution_time=0.5,
                model="test",
            )

    # Original file should still be intact and valid
    assert conv_file.read_text() == original_data
    reloaded = WebConversationSession(session_dir)
    assert len(reloaded.list_exchanges()) == 1
    assert reloaded.list_exchanges()[0]["question"] == "Q1"

    # No leftover temp files
    tmp_files = list(session_dir.glob("_conversation.json.*"))
    assert tmp_files == []


def test_add_exchange_stores_gave_up(session: WebConversationSession) -> None:
    """add_exchange stores gave_up flag when provided."""
    exchange = session.add_exchange(
        question="What?",
        answer="Partial evidence.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
        gave_up=True,
    )
    assert exchange["gave_up"] is True
    reloaded = WebConversationSession(session._file.parent)
    assert reloaded.list_exchanges()[0]["gave_up"] is True


def test_add_exchange_gave_up_defaults_to_false(session: WebConversationSession) -> None:
    """gave_up defaults to False when not provided."""
    exchange = session.add_exchange(
        question="What?",
        answer="Full answer.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert exchange["gave_up"] is False


def test_add_exchange_document_ids_defaults_to_none(session: WebConversationSession) -> None:
    """add_exchange works without document_ids for backward compatibility."""
    exchange = session.add_exchange(
        question="What?",
        answer="Something.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert exchange.get("document_ids") is None


def test_uses_underscore_conversation_file(session_dir: Path) -> None:
    """Web session persists to _conversation.json for backward compatibility."""
    session_dir.mkdir(parents=True, exist_ok=True)
    s = WebConversationSession(session_dir)
    s.add_exchange(
        question="Q",
        answer="A",
        trace_id="t",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert (session_dir / "_conversation.json").exists()
    # Should NOT create the shared module's default file
    assert not (session_dir / "conversation.json").exists()


def test_inherits_from_shared_session() -> None:
    """WebConversationSession is a subclass of the shared session."""
    from ananta.experimental.shared.session import (
        WebConversationSession as SharedSession,
    )

    assert issubclass(WebConversationSession, SharedSession)
