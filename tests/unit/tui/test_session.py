"""Tests for TUI conversation session."""

import pytest

from ananta.tui.session import ConversationSession


class TestConversationSession:
    """Tests for ConversationSession."""

    def test_empty_session(self) -> None:
        """New session has no exchanges."""
        session = ConversationSession(project_name="test")
        assert session.exchange_count == 0
        assert session.format_history_prefix() == ""

    def test_add_exchange(self) -> None:
        """Adding an exchange increments count."""
        session = ConversationSession(project_name="test")
        session.add_exchange("question", "answer", "stats")
        assert session.exchange_count == 1

    def test_format_history_prefix(self) -> None:
        """History prefix formats previous Q&A."""
        session = ConversationSession(project_name="test")
        session.add_exchange("Who is X?", "X is Y.", "stats")
        prefix = session.format_history_prefix()
        assert "Q1: Who is X?" in prefix
        assert "A1: X is Y." in prefix
        assert prefix.endswith("Current question:\n")

    def test_should_warn_by_exchanges(self) -> None:
        """Warns when exchange count exceeds threshold."""
        session = ConversationSession(project_name="test", warn_exchanges=2)
        session.add_exchange("q1", "a1", "s1")
        assert session.should_warn_history_size() is False
        session.add_exchange("q2", "a2", "s2")
        assert session.should_warn_history_size() is True

    def test_should_warn_by_chars(self) -> None:
        """Warns when total chars exceed threshold."""
        session = ConversationSession(project_name="test", warn_chars=20)
        session.add_exchange("short", "short", "s")
        assert session.should_warn_history_size() is False
        session.add_exchange("a" * 20, "b" * 20, "s")
        assert session.should_warn_history_size() is True

    def test_clear_history(self) -> None:
        """Clear removes all exchanges."""
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        session.clear_history()
        assert session.exchange_count == 0
        assert session.format_history_prefix() == ""

    def test_format_transcript(self) -> None:
        """Transcript includes project name and exchanges."""
        session = ConversationSession(project_name="barsoom")
        session.add_exchange("Who is X?", "X is Y.", "---\nTime: 1s")
        transcript = session.format_transcript()
        assert "barsoom" in transcript
        assert "Who is X?" in transcript
        assert "X is Y." in transcript

    def test_write_transcript(self, tmp_path: object) -> None:
        """Write transcript creates file."""
        from pathlib import Path

        tmp = Path(str(tmp_path))
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        path = session.write_transcript(str(tmp / "out.md"))
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "test" in content

    def test_write_transcript_auto_filename(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Write transcript with None filename auto-generates name."""
        from pathlib import Path

        monkeypatch.chdir(Path(str(tmp_path)))
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        path = session.write_transcript(None)
        assert "session-" in path
        assert path.endswith(".md")
