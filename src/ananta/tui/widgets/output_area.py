"""Scrolling output area widget."""

from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static


class OutputArea(VerticalScroll):
    """Scrolling container for conversation output.

    Displays user messages and LLM responses. Supports toggling
    between markdown rendering and plain text for responses.
    """

    DEFAULT_CSS = """
    OutputArea {
        height: 1fr;
        padding: 0 1;
    }
    OutputArea:focus {
        border: solid #00bcd4;
    }
    OutputArea .user-message {
        color: $accent;
        margin-top: 1;
    }
    OutputArea .thought-time {
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.markdown_enabled: bool = True

    def add_user_message(self, text: str) -> None:
        """Add a user message to the output."""
        widget = Static(f"\u276f {text}", classes="user-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def add_response(self, text: str, thought_seconds: float) -> None:
        """Add an LLM response with thought time."""
        seconds = round(thought_seconds)
        unit = "second" if seconds == 1 else "seconds"
        time_widget = Static(f"[Thought for {seconds} {unit}]", classes="thought-time")
        self.mount(time_widget)

        if self.markdown_enabled:
            self.mount(Markdown(text))
        else:
            self.mount(Static(text))
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        """Add a system/info message to the output."""
        widget = Static(text, classes="system-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def clear(self) -> None:
        """Remove all child widgets from the output area."""
        for child in list(self.children):
            child.remove()

    def add_system_markdown(self, text: str) -> None:
        """Add a system message with markdown rendering support.

        Respects the markdown_enabled toggle: renders with Markdown
        when on, Static when off.
        """
        if self.markdown_enabled:
            self.mount(Markdown(text))
        else:
            self.mount(Static(text, classes="system-message"))
        self.scroll_end(animate=False)
