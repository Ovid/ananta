"""Fallback parser for any text file not matched by specialized parsers."""

from pathlib import Path

import chardet

from shesha.models import ParsedDocument


class FallbackTextParser:
    """Fallback parser that accepts any non-binary file.

    This parser should be registered last in the parser chain. It catches
    any text file that wasn't matched by specialized parsers (unknown
    programming languages, config files, etc.).
    """

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Accept any file that appears to be text (not binary)."""
        try:
            with open(path, "rb") as f:
                # Read first 8KB to check for binary content
                chunk = f.read(8192)

            # Empty files are text
            if not chunk:
                return True

            # Null bytes indicate binary
            if b"\x00" in chunk:
                return False

            return True
        except OSError:
            return False

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse file as plain text with optional line numbers.

        Args:
            path: Path to the file to parse.
            include_line_numbers: Whether to prefix lines with numbers.
            file_path: Display path for the file.
        """
        # Detect encoding
        with open(path, "rb") as f:
            raw = f.read()

        detected = chardet.detect(raw)
        encoding = detected.get("encoding") or "utf-8"

        try:
            content = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            content = raw.decode("utf-8", errors="replace")

        if include_line_numbers:
            display_path = file_path or path.name
            lines = content.splitlines()
            width = len(str(len(lines)))
            numbered = [f"=== FILE: {display_path} ==="]
            numbered.extend(f"{i + 1:>{width}}| {line}" for i, line in enumerate(lines))
            content = "\n".join(numbered)

        # Use extension as format, or "text" if none
        ext = path.suffix.lstrip(".").lower()
        format_type = ext if ext else "text"

        return ParsedDocument(
            name=file_path or path.name,
            content=content,
            format=format_type,
            metadata={},
            char_count=len(content),
        )
