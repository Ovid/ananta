"""Input history for TUI prompt."""


class InputHistory:
    """In-memory input history with up/down navigation.

    Entries are stored in order of addition. Navigation uses an internal
    cursor that starts past the end (current input). previous() moves
    backward, next() moves forward.
    """

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._cursor: int = 0

    def add(self, entry: str) -> None:
        """Add an entry to history. Skips consecutive duplicates."""
        if self._entries and self._entries[-1] == entry:
            self._cursor = len(self._entries)
            return
        self._entries.append(entry)
        self._cursor = len(self._entries)

    def previous(self) -> str | None:
        """Move cursor back and return entry, or None if at start."""
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        return self._entries[self._cursor]

    def next(self) -> str | None:
        """Move cursor forward and return entry, or None if at end."""
        if self._cursor >= len(self._entries) - 1:
            self._cursor = len(self._entries)
            return None
        self._cursor += 1
        return self._entries[self._cursor]
