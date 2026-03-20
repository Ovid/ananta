"""Document parser protocol."""

from pathlib import Path
from typing import Protocol

from shesha.models import ParsedDocument


class DocumentParser(Protocol):
    """Protocol for document parsers."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        ...

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse a file and return a ParsedDocument.

        Args:
            path: Path to the file to parse.
            include_line_numbers: If True, format with line numbers and file header.
            file_path: Path to show in the file header (defaults to path.name).
        """
        ...
