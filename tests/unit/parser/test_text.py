"""Tests for text file parser."""

from pathlib import Path

import pytest

from ananta.parser.text import TextParser


@pytest.fixture
def parser() -> TextParser:
    return TextParser()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent.parent / "fixtures"


class TestTextParser:
    """Tests for TextParser."""

    def test_can_parse_txt(self, parser: TextParser):
        """TextParser can parse .txt files."""
        assert parser.can_parse(Path("test.txt"))

    def test_can_parse_md(self, parser: TextParser):
        """TextParser can parse .md files."""
        assert parser.can_parse(Path("test.md"))

    def test_can_parse_json(self, parser: TextParser):
        """TextParser can parse .json files."""
        assert parser.can_parse(Path("test.json"))

    def test_cannot_parse_binary(self, parser: TextParser):
        """TextParser cannot parse binary files."""
        assert not parser.can_parse(Path("test.pdf"))
        assert not parser.can_parse(Path("test.docx"))

    def test_parse_txt_file(self, parser: TextParser, fixtures_dir: Path):
        """TextParser extracts content from .txt files."""
        doc = parser.parse(fixtures_dir / "sample.txt")
        assert doc.name == "sample.txt"
        assert "test file" in doc.content
        assert doc.format == "txt"

    def test_parse_md_file(self, parser: TextParser, fixtures_dir: Path):
        """TextParser extracts content from .md files."""
        doc = parser.parse(fixtures_dir / "sample.md")
        assert doc.name == "sample.md"
        assert "Markdown" in doc.content
        assert doc.format == "md"

    def test_parse_json_file(self, parser: TextParser, fixtures_dir: Path):
        """TextParser pretty-prints JSON content."""
        doc = parser.parse(fixtures_dir / "sample.json")
        assert doc.name == "sample.json"
        assert "key" in doc.content
        assert doc.format == "json"

    def test_parse_csv_file(self, parser: TextParser, fixtures_dir: Path):
        """TextParser converts CSV to readable table format."""
        doc = parser.parse(fixtures_dir / "sample.csv")
        assert doc.name == "sample.csv"
        assert "name" in doc.content
        assert "Alice" in doc.content
        assert doc.format == "csv"
