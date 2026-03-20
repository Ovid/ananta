"""Code file parser for source code files."""

from pathlib import Path

import chardet

from shesha.models import ParsedDocument

# Map extensions to language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".pl": "perl",
    ".pm": "perl",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
}

# Map shebang interpreters to language names
SHEBANG_TO_LANGUAGE: dict[str, str] = {
    "bash": "bash",
    "sh": "bash",
    "zsh": "zsh",
    "python": "python",
    "python3": "python",
    "ruby": "ruby",
    "perl": "perl",
    "node": "javascript",
    "php": "php",
}


class CodeParser:
    """Parser for source code files."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        if path.suffix.lower() in EXTENSION_TO_LANGUAGE:
            return True
        if not path.suffix:
            return self._has_valid_shebang(path)
        return False

    def _has_valid_shebang(self, path: Path) -> bool:
        """Check if file has a valid shebang line (and is not binary)."""
        try:
            with open(path, "rb") as f:
                header = f.read(512)
            # Check for null bytes (binary file indicator)
            if b"\x00" in header:
                return False
            first_line = header.split(b"\n")[0].decode("utf-8", errors="ignore")
            if first_line.startswith("#!"):
                return self._parse_shebang(first_line) is not None
            return False
        except OSError:
            return False

    def _parse_shebang(self, shebang_line: str) -> str | None:
        """Extract language from shebang line."""
        parts = shebang_line[2:].strip().split()
        if not parts:
            return None
        # Handle /usr/bin/env style shebangs
        if parts[0].endswith("/env") and len(parts) > 1:
            interpreter = parts[1]
        else:
            interpreter = parts[0].split("/")[-1]
        # Strip version numbers (e.g., python3 -> python)
        base_interpreter = interpreter.rstrip("0123456789.")
        return SHEBANG_TO_LANGUAGE.get(base_interpreter)

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse a code file and return a ParsedDocument.

        Args:
            path: Path to the file to parse.
            include_line_numbers: If True, format with line numbers and file header.
            file_path: Path to show in the file header (defaults to path.name).
        """
        content, encoding = self._read_with_encoding_detection(path)
        ext = path.suffix.lower()
        language = EXTENSION_TO_LANGUAGE.get(ext)
        if language is None:
            # Try shebang detection for extensionless files
            first_line = content.split("\n")[0] if content else ""
            if first_line.startswith("#!"):
                language = self._parse_shebang(first_line)
            language = language or "unknown"

        if include_line_numbers:
            display_path = file_path or path.name
            content = self._format_with_line_numbers(content, display_path)

        return ParsedDocument(
            name=path.name,
            content=content,
            # For extensionless files, format is empty - language is in metadata
            format=ext.lstrip("."),
            metadata={"language": language, "encoding": encoding},
            char_count=len(content),
            parse_warnings=[],
        )

    def _format_with_line_numbers(self, content: str, file_path: str) -> str:
        """Format content with file header and line numbers."""
        lines = content.split("\n")
        total_lines = len(lines)
        # Calculate padding width (at least 1 digit)
        width = len(str(total_lines)) if total_lines > 0 else 1

        formatted_lines = [f"=== FILE: {file_path} ==="]
        for i, line in enumerate(lines, start=1):
            formatted_lines.append(f"{i:>{width}}| {line}")

        return "\n".join(formatted_lines)

    def _read_with_encoding_detection(self, path: Path) -> tuple[str, str]:
        """Read file with automatic encoding detection."""
        raw_bytes = path.read_bytes()

        # Try UTF-8 first (most common)
        try:
            return raw_bytes.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass

        # Fall back to chardet detection
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding") or "utf-8"

        try:
            return raw_bytes.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            # Last resort: decode with errors replaced
            return raw_bytes.decode("utf-8", errors="replace"), "utf-8"
