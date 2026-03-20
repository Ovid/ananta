"""Tests for completion popup widget."""

from ananta.tui.widgets.completion_popup import CompletionPopup


class TestCompletionPopup:
    """Tests for CompletionPopup widget."""

    def test_initially_hidden(self) -> None:
        """Popup is hidden and has no selection by default."""
        popup = CompletionPopup()
        assert popup.is_visible is False
        assert popup.selected_value is None

    def test_show_items_sets_visible(self) -> None:
        """show_items() makes the popup visible."""
        popup = CompletionPopup()
        popup.show_items([("/help", "Show available commands")])
        assert popup.is_visible is True

    def test_hide_clears_state(self) -> None:
        """hide() makes the popup invisible and clears selection."""
        popup = CompletionPopup()
        popup.show_items([("/help", "Show available commands")])
        popup.hide()
        assert popup.is_visible is False
        assert popup.selected_value is None

    def test_select_next_wraps(self) -> None:
        """select_next() wraps from last item to first."""
        popup = CompletionPopup()
        popup.show_items(
            [
                ("/help", "Show available commands"),
                ("/quit", "Exit"),
            ]
        )
        assert popup.select_next() == 1
        assert popup.select_next() == 0  # wraps

    def test_select_prev_wraps(self) -> None:
        """select_prev() wraps from first item to last."""
        popup = CompletionPopup()
        popup.show_items(
            [
                ("/help", "Show available commands"),
                ("/quit", "Exit"),
            ]
        )
        # selected starts at 0, prev should wrap to last
        assert popup.select_prev() == 1  # wraps to last
        assert popup.select_prev() == 0

    def test_selected_value(self) -> None:
        """selected_value returns the command name of the selected item."""
        popup = CompletionPopup()
        popup.show_items(
            [
                ("/help", "Show available commands"),
                ("/quit", "Exit"),
            ]
        )
        assert popup.selected_value == "/help"
        popup.select_next()
        assert popup.selected_value == "/quit"
