"""Conversation session for TUI."""

from datetime import datetime
from pathlib import Path


class ConversationSession:
    """Manages conversation history, context formatting, and transcript export.

    Args:
        project_name: Name of the project for transcript metadata.
        warn_exchanges: Warn when exchange count reaches this threshold.
        warn_chars: Warn when total chars reach this threshold.
    """

    def __init__(
        self,
        project_name: str,
        warn_exchanges: int = 10,
        warn_chars: int = 50_000,
    ) -> None:
        self.project_name = project_name
        self._warn_exchanges = warn_exchanges
        self._warn_chars = warn_chars
        self._history: list[tuple[str, str, str]] = []

    @property
    def exchange_count(self) -> int:
        """Number of exchanges in history."""
        return len(self._history)

    def add_exchange(self, question: str, answer: str, stats: str) -> None:
        """Add a Q&A exchange to history."""
        self._history.append((question, answer, stats))

    def clear_history(self) -> None:
        """Clear all history."""
        self._history.clear()

    def format_history_prefix(self) -> str:
        """Format history as context prefix for follow-up questions."""
        if not self._history:
            return ""
        lines = ["Previous conversation:"]
        for i, (q, a, _stats) in enumerate(self._history, 1):
            lines.append(f"Q{i}: {q}")
            lines.append(f"A{i}: {a}")
            lines.append("")
        lines.append("Current question:\n")
        return "\n".join(lines)

    def should_warn_history_size(self) -> bool:
        """Check if history is large enough to warrant a warning."""
        if len(self._history) >= self._warn_exchanges:
            return True
        total_chars = sum(len(q) + len(a) for q, a, _s in self._history)
        return total_chars >= self._warn_chars

    def format_transcript(self) -> str:
        """Format history as a markdown transcript."""
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Session Transcript",
            "",
            f"- **Date:** {date_str}",
            f"- **Project:** {self.project_name}",
            f"- **Exchanges:** {len(self._history)}",
            "",
            "---",
        ]
        for question, answer, stats in self._history:
            lines.extend(["", f"**User:** {question}", "", answer, "", stats, "", "---"])
        return "\n".join(lines)

    def write_transcript(self, filename: str | None) -> str:
        """Write transcript to file. Auto-generates name if None."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            filename = f"session-{timestamp}.md"
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(self.format_transcript(), encoding="utf-8")
        return str(filepath)
