"""Tests for HTML parser."""

from pathlib import Path

import pytest

from ananta.parser.html import HtmlParser


@pytest.fixture
def parser() -> HtmlParser:
    return HtmlParser()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent.parent / "fixtures"


class TestHtmlParser:
    """Tests for HtmlParser."""

    def test_can_parse_html(self, parser: HtmlParser):
        """HtmlParser can parse .html files."""
        assert parser.can_parse(Path("page.html"))
        assert parser.can_parse(Path("page.htm"))

    def test_cannot_parse_other(self, parser: HtmlParser):
        """HtmlParser cannot parse non-HTML files."""
        assert not parser.can_parse(Path("page.txt"))

    def test_parse_html_extracts_text(self, parser: HtmlParser, fixtures_dir: Path):
        """HtmlParser extracts text content, stripping tags."""
        doc = parser.parse(fixtures_dir / "sample.html")
        assert doc.name == "sample.html"
        assert "Welcome" in doc.content
        assert "test" in doc.content
        assert "<h1>" not in doc.content  # Tags stripped
        assert "console.log" not in doc.content  # Script removed
        assert doc.format == "html"
