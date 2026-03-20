"""Tests for TUI input history."""

from ananta.tui.history import InputHistory


class TestInputHistory:
    """Tests for InputHistory."""

    def test_empty_history_previous_returns_none(self) -> None:
        """Previous on empty history returns None."""
        h = InputHistory()
        assert h.previous() is None

    def test_empty_history_next_returns_none(self) -> None:
        """Next on empty history returns None."""
        h = InputHistory()
        assert h.next() is None

    def test_add_and_previous(self) -> None:
        """Can retrieve last entry with previous()."""
        h = InputHistory()
        h.add("hello")
        assert h.previous() == "hello"

    def test_multiple_entries_navigation(self) -> None:
        """Previous walks backward, next walks forward."""
        h = InputHistory()
        h.add("first")
        h.add("second")
        h.add("third")
        assert h.previous() == "third"
        assert h.previous() == "second"
        assert h.previous() == "first"
        assert h.previous() is None  # at start, stays put
        assert h.next() == "second"
        assert h.next() == "third"
        assert h.next() is None  # back to current (empty)

    def test_add_resets_position(self) -> None:
        """Adding an entry resets navigation to end."""
        h = InputHistory()
        h.add("first")
        h.add("second")
        h.previous()  # "second"
        h.previous()  # "first"
        h.add("third")
        assert h.previous() == "third"

    def test_duplicate_consecutive_not_added(self) -> None:
        """Consecutive duplicates are not added."""
        h = InputHistory()
        h.add("hello")
        h.add("hello")
        assert h.previous() == "hello"
        assert h.previous() is None  # only one entry
