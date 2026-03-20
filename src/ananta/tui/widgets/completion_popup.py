"""Completion popup widget for slash command auto-complete."""

from textual.widgets import Static


class CompletionPopup(Static):
    """Popup widget displaying command completion suggestions.

    A pure display widget that shows matching slash commands with
    a highlighted selection. Hidden by default.
    """

    DEFAULT_CSS = """
    CompletionPopup {
        height: auto;
        max-height: 20;
        display: none;
        border: solid $accent;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("")
        self._items: list[tuple[str, str]] = []
        self._selected: int = 0

    @property
    def is_visible(self) -> bool:
        """True when the popup has items to display."""
        return len(self._items) > 0

    @property
    def selected_value(self) -> str | None:
        """Return the command name of the currently selected item."""
        if not self._items:
            return None
        return self._items[self._selected][0]

    def show_items(self, items: list[tuple[str, str]], selected: int = 0) -> None:
        """Show the popup with the given items.

        Args:
            items: List of (command_name, description) tuples.
            selected: Index of the initially selected item.
        """
        self._items = list(items)
        self._selected = selected
        self._render_items()
        self.display = True

    def hide(self) -> None:
        """Hide the popup and clear state."""
        self._items = []
        self._selected = 0
        self.update("")
        self.display = False

    def select_next(self) -> int:
        """Move selection forward, wrapping at the end."""
        if self._items:
            self._selected = (self._selected + 1) % len(self._items)
            self._render_items()
        return self._selected

    def select_prev(self) -> int:
        """Move selection backward, wrapping at the start."""
        if self._items:
            self._selected = (self._selected - 1) % len(self._items)
            self._render_items()
        return self._selected

    def _render_items(self) -> None:
        """Re-render the popup content."""
        lines = []
        for i, (name, desc) in enumerate(self._items):
            marker = ">" if i == self._selected else " "
            lines.append(f"{marker} {name:20s} {desc}")
        self.update("\n".join(lines))
