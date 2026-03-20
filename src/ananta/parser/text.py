"""Text file parser for plain text, markdown, JSON, and CSV files."""

import csv
import json
from io import StringIO
from pathlib import Path

from shesha.models import ParsedDocument


class TextParser:
    """Parser for text-based files."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv", ".yaml", ".yml"}

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse a text file and return a ParsedDocument.

        Args:
            path: Path to the file to parse.
            include_line_numbers: Ignored for text files.
            file_path: Ignored for text files.
        """
        content = path.read_text(encoding="utf-8")
        format_type = path.suffix.lstrip(".").lower()

        # Pretty-print JSON for readability
        if format_type == "json":
            try:
                data = json.loads(content)
                content = json.dumps(data, indent=2)
            except json.JSONDecodeError:
                pass  # Keep original content if invalid JSON

        # Convert CSV to readable table format
        elif format_type == "csv":
            try:
                reader = csv.reader(StringIO(content))
                rows = list(reader)
                if rows:
                    # Calculate column widths
                    col_widths = [max(len(str(cell)) for cell in col) for col in zip(*rows)]
                    # Format as aligned table
                    lines = []
                    for i, row in enumerate(rows):
                        line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths))
                        lines.append(line)
                        if i == 0:  # Add separator after header
                            lines.append("-+-".join("-" * w for w in col_widths))
                    content = "\n".join(lines)
            except csv.Error:
                pass  # Keep original content if invalid CSV

        return ParsedDocument(
            name=path.name,
            content=content,
            format=format_type,
            metadata={"encoding": "utf-8"},
            char_count=len(content),
            parse_warnings=[],
        )
