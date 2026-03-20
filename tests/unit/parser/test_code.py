"""Tests for code file parser."""

from pathlib import Path

import pytest

from ananta.parser.code import CodeParser


@pytest.fixture
def parser() -> CodeParser:
    return CodeParser()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent.parent / "fixtures"


class TestCodeParser:
    """Tests for CodeParser."""

    def test_can_parse_python(self, parser: CodeParser):
        """CodeParser can parse .py files."""
        assert parser.can_parse(Path("test.py"))

    def test_can_parse_javascript(self, parser: CodeParser):
        """CodeParser can parse .js files."""
        assert parser.can_parse(Path("test.js"))

    def test_can_parse_typescript(self, parser: CodeParser):
        """CodeParser can parse .ts files."""
        assert parser.can_parse(Path("test.ts"))

    def test_cannot_parse_text(self, parser: CodeParser):
        """CodeParser doesn't handle plain text."""
        assert not parser.can_parse(Path("test.txt"))

    def test_parse_python_file(self, parser: CodeParser, fixtures_dir: Path):
        """CodeParser extracts Python code with language metadata."""
        doc = parser.parse(fixtures_dir / "sample.py")
        assert doc.name == "sample.py"
        assert "def hello" in doc.content
        assert doc.format == "py"
        assert doc.metadata["language"] == "python"

    def test_parse_javascript_file(self, parser: CodeParser, fixtures_dir: Path):
        """CodeParser extracts JavaScript code with language metadata."""
        doc = parser.parse(fixtures_dir / "sample.js")
        assert doc.name == "sample.js"
        assert "function hello" in doc.content
        assert doc.format == "js"
        assert doc.metadata["language"] == "javascript"

    def test_parse_with_line_numbers(self, parser: CodeParser, fixtures_dir: Path):
        """CodeParser formats with line numbers when enabled."""
        doc = parser.parse(
            fixtures_dir / "sample.py",
            include_line_numbers=True,
            file_path="src/sample.py",
        )

        # Should have file header
        assert "=== FILE: src/sample.py ===" in doc.content

        # Should have line numbers
        lines = doc.content.split("\n")
        # First line is header, second is content
        assert lines[1].strip().startswith("1|")

    def test_line_number_padding_adjusts(self, parser: CodeParser, tmp_path: Path):
        """Line number padding adjusts to file length."""
        # Create a file with 100+ lines
        content = "\n".join([f"line {i}" for i in range(150)])
        test_file = tmp_path / "many_lines.py"
        test_file.write_text(content)

        doc = parser.parse(test_file, include_line_numbers=True, file_path="many_lines.py")
        lines = doc.content.split("\n")

        # Line 1 should be padded to 3 digits (for 150 lines)
        assert "  1|" in lines[1]
        # Line 100 should be padded to 3 digits
        assert "100|" in lines[100]

    def test_parse_non_utf8_file(self, parser: CodeParser, tmp_path: Path):
        """CodeParser handles non-UTF-8 files via chardet."""
        # Create a Latin-1 encoded file
        content = "# Comment with accent: café"
        test_file = tmp_path / "latin1.py"
        test_file.write_bytes(content.encode("latin-1"))

        doc = parser.parse(test_file)
        assert "caf" in doc.content  # Should decode successfully
        assert doc.metadata["encoding"] in ["latin-1", "ISO-8859-1", "Windows-1252"]

    def test_can_parse_extensionless_with_shebang(self, parser: CodeParser, tmp_path: Path):
        """CodeParser can parse extensionless files with shebangs."""
        test_file = tmp_path / "myscript"
        test_file.write_text("#!/bin/bash\necho hello")

        assert parser.can_parse(test_file)

    def test_parse_bash_shebang(self, parser: CodeParser, tmp_path: Path):
        """CodeParser detects bash from shebang."""
        test_file = tmp_path / "myscript"
        test_file.write_text("#!/bin/bash\necho hello")

        doc = parser.parse(test_file)
        assert doc.metadata["language"] == "bash"

    def test_parse_python_env_shebang(self, parser: CodeParser, tmp_path: Path):
        """CodeParser detects python from env shebang."""
        test_file = tmp_path / "myscript"
        test_file.write_text("#!/usr/bin/env python3\nprint('hello')")

        doc = parser.parse(test_file)
        assert doc.metadata["language"] == "python"

    def test_cannot_parse_binary_extensionless(self, parser: CodeParser, tmp_path: Path):
        """CodeParser rejects binary extensionless files."""
        test_file = tmp_path / "binary"
        test_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        assert not parser.can_parse(test_file)
