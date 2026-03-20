"""Input area widget with multiline support."""

import re

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class InputSubmitted(Message):
    """Posted when the user submits input."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class InputArea(TextArea):
    """Input widget for the TUI prompt.

    Enter submits. Ctrl+J inserts a newline (works in all terminals).
    Alt+Enter and Shift+Enter also insert newlines in terminals that
    support them. A trailing backslash prevents submission and continues
    on the next line; backslash-newline pairs are joined on submission.
    """

    DEFAULT_CSS = """
    InputArea {
        height: auto;
        min-height: 1;
        max-height: 10;
        border: none;
    }
    InputArea:focus {
        border: none;
    }
    """

    BINDINGS = []  # Override default TextArea bindings

    class CompletionNavigate(Message):
        """Posted when user navigates the completion popup."""

        def __init__(self, direction: str) -> None:
            super().__init__()
            self.direction = direction

    class CompletionAccept(Message):
        """Posted when user accepts a completion."""

    class CompletionDismiss(Message):
        """Posted when user dismisses the completion popup."""

    class FocusToggle(Message):
        """Posted when user presses Tab to toggle focus between panes."""

    class HistoryNavigate(Message):
        """Posted when user navigates input history with up/down arrows."""

        def __init__(self, direction: str) -> None:
            super().__init__()
            self.direction = direction

    class QueryCancelled(Message):
        """Posted when user double-escapes to cancel a query."""

    def __init__(self) -> None:
        super().__init__(language=None, show_line_numbers=False)
        self._query_in_progress = False
        self._completion_active = False

    @property
    def query_in_progress(self) -> bool:
        """Whether a query is currently running."""
        return self._query_in_progress

    @query_in_progress.setter
    def query_in_progress(self, value: bool) -> None:
        self._query_in_progress = value

    @property
    def completion_active(self) -> bool:
        """Whether completion popup is active."""
        return self._completion_active

    @completion_active.setter
    def completion_active(self, value: bool) -> None:
        self._completion_active = value

    async def _on_key(self, event: events.Key) -> None:
        """Handle key events."""
        # Completion key handling takes priority when active
        if self._completion_active:
            if event.key in ("tab", "enter"):
                event.prevent_default()
                event.stop()
                self.post_message(InputArea.CompletionAccept())
                return
            if event.key == "down":
                event.prevent_default()
                event.stop()
                self.post_message(InputArea.CompletionNavigate("next"))
                return
            if event.key == "up":
                event.prevent_default()
                event.stop()
                self.post_message(InputArea.CompletionNavigate("prev"))
                return
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self.post_message(InputArea.CompletionDismiss())
                return

        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self.post_message(InputArea.FocusToggle())
            return

        if event.key == "up":
            event.prevent_default()
            event.stop()
            self.post_message(InputArea.HistoryNavigate("prev"))
            return

        if event.key == "down":
            event.prevent_default()
            event.stop()
            self.post_message(InputArea.HistoryNavigate("next"))
            return

        if event.key in ("shift+enter", "alt+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if not text:
                return
            # Trailing backslash means "continue on next line"
            if text.endswith("\\"):
                self.insert("\n")
                return
            # Clean up backslash continuation markers before submitting
            cleaned = re.sub(r"\\\n", "\n", text)
            self.post_message(InputSubmitted(cleaned))
            self.text = ""
            return

        if event.key == "escape":
            event.prevent_default()
            event.stop()
            if self.text:
                self.text = ""
            elif self._query_in_progress:
                self.post_message(InputArea.QueryCancelled())
            return

        # Let TextArea handle everything else
        await super()._on_key(event)
