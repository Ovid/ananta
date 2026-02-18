"""Tests for fallback text parser."""

from pathlib import Path

from shesha.parser.fallback import FallbackTextParser


class TestFallbackCanParse:
    """Tests for FallbackTextParser.can_parse method."""

    def test_can_parse_returns_true_for_text_file(self, tmp_path: Path) -> None:
        """can_parse returns True for plain text file."""
        parser = FallbackTextParser()
        text_file = tmp_path / "unknown.xyz"
        text_file.write_text("Hello, world!")

        assert parser.can_parse(text_file) is True

    def test_can_parse_returns_true_for_empty_file(self, tmp_path: Path) -> None:
        """can_parse returns True for empty files (they're text)."""
        parser = FallbackTextParser()
        empty_file = tmp_path / "empty.xyz"
        empty_file.write_bytes(b"")

        assert parser.can_parse(empty_file) is True

    def test_can_parse_returns_false_for_binary_file(self, tmp_path: Path) -> None:
        """can_parse returns False for binary files (containing null bytes)."""
        parser = FallbackTextParser()
        binary_file = tmp_path / "binary.xyz"
        binary_file.write_bytes(b"Hello\x00World")

        assert parser.can_parse(binary_file) is False

    def test_can_parse_returns_false_for_nonexistent_file(self, tmp_path: Path) -> None:
        """can_parse returns False for files that don't exist."""
        parser = FallbackTextParser()
        missing = tmp_path / "does_not_exist.xyz"

        assert parser.can_parse(missing) is False

    def test_can_parse_detects_binary_in_first_8kb(self, tmp_path: Path) -> None:
        """can_parse detects binary content in first 8KB."""
        parser = FallbackTextParser()
        # Binary indicator in middle of first 8KB
        content = b"A" * 4000 + b"\x00" + b"B" * 4000
        binary_file = tmp_path / "late_binary.xyz"
        binary_file.write_bytes(content)

        assert parser.can_parse(binary_file) is False

    def test_can_parse_ignores_null_after_8kb(self, tmp_path: Path) -> None:
        """can_parse only checks first 8KB for binary indicators."""
        parser = FallbackTextParser()
        # Null byte after 8KB mark
        content = b"A" * 9000 + b"\x00" + b"B" * 1000
        mixed_file = tmp_path / "mixed.xyz"
        mixed_file.write_bytes(content)

        # Should return True because null is beyond 8KB
        assert parser.can_parse(mixed_file) is True


class TestFallbackParse:
    """Tests for FallbackTextParser.parse method."""

    def test_parse_returns_parsed_document(self, tmp_path: Path) -> None:
        """parse returns a ParsedDocument with content."""
        parser = FallbackTextParser()
        text_file = tmp_path / "file.unknown"
        text_file.write_text("Some content here")

        doc = parser.parse(text_file)

        assert doc.content == "Some content here"
        assert doc.name == "file.unknown"
        assert doc.format == "unknown"

    def test_parse_uses_extension_as_format(self, tmp_path: Path) -> None:
        """parse uses file extension as format type."""
        parser = FallbackTextParser()
        text_file = tmp_path / "config.ini"
        text_file.write_text("[section]\nkey=value")

        doc = parser.parse(text_file)

        assert doc.format == "ini"

    def test_parse_uses_text_format_for_extensionless(self, tmp_path: Path) -> None:
        """parse uses 'text' as format for files without extension."""
        parser = FallbackTextParser()
        text_file = tmp_path / "Makefile"
        text_file.write_text("all: build")

        doc = parser.parse(text_file)

        assert doc.format == "text"

    def test_parse_adds_line_numbers_when_requested(self, tmp_path: Path) -> None:
        """parse adds line numbers when include_line_numbers is True."""
        parser = FallbackTextParser()
        text_file = tmp_path / "script.sh"
        text_file.write_text("#!/bin/bash\necho hello\nexit 0")

        doc = parser.parse(text_file, include_line_numbers=True)

        assert "1| #!/bin/bash" in doc.content
        assert "2| echo hello" in doc.content
        assert "3| exit 0" in doc.content

    def test_parse_includes_file_header_with_line_numbers(self, tmp_path: Path) -> None:
        """parse prepends === FILE: path === header when include_line_numbers is True."""
        parser = FallbackTextParser()
        text_file = tmp_path / "readme.md"
        text_file.write_text("# Hello\nWorld")

        doc = parser.parse(text_file, include_line_numbers=True, file_path="docs/readme.md")

        assert doc.content.startswith("=== FILE: docs/readme.md ===\n")

    def test_parse_file_header_uses_basename_without_file_path(self, tmp_path: Path) -> None:
        """parse uses path.name for header when file_path is not provided."""
        parser = FallbackTextParser()
        text_file = tmp_path / "config.yml"
        text_file.write_text("key: value")

        doc = parser.parse(text_file, include_line_numbers=True)

        assert doc.content.startswith("=== FILE: config.yml ===\n")

    def test_parse_no_file_header_without_line_numbers(self, tmp_path: Path) -> None:
        """parse does not add file header when include_line_numbers is False."""
        parser = FallbackTextParser()
        text_file = tmp_path / "readme.md"
        text_file.write_text("# Hello")

        doc = parser.parse(text_file)

        assert not doc.content.startswith("=== FILE:")

    def test_parse_respects_file_path_override(self, tmp_path: Path) -> None:
        """parse uses file_path parameter for document name."""
        parser = FallbackTextParser()
        text_file = tmp_path / "actual.txt"
        text_file.write_text("content")

        doc = parser.parse(text_file, file_path="display/path.txt")

        assert doc.name == "display/path.txt"

    def test_parse_detects_encoding(self, tmp_path: Path) -> None:
        """parse detects and uses correct encoding."""
        parser = FallbackTextParser()
        text_file = tmp_path / "utf8.txt"
        text_file.write_text("Héllo wörld", encoding="utf-8")

        doc = parser.parse(text_file)

        assert "Héllo wörld" in doc.content

    def test_parse_handles_latin1_encoding(self, tmp_path: Path) -> None:
        """parse handles non-UTF8 encodings like Latin-1."""
        parser = FallbackTextParser()
        text_file = tmp_path / "latin1.txt"
        text_file.write_bytes("café résumé".encode("latin-1"))

        doc = parser.parse(text_file)

        # Should decode successfully (exact result depends on chardet detection)
        assert len(doc.content) > 0
        assert doc.char_count > 0

    def test_parse_calculates_char_count(self, tmp_path: Path) -> None:
        """parse calculates correct character count."""
        parser = FallbackTextParser()
        text_file = tmp_path / "count.txt"
        text_file.write_text("1234567890")

        doc = parser.parse(text_file)

        assert doc.char_count == 10
