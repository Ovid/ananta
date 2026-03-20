"""Tests for parser registry."""

from pathlib import Path

from ananta.parser.base import DocumentParser
from ananta.parser.registry import ParserRegistry
from ananta.storage.base import ParsedDocument


class MockParser(DocumentParser):
    """A mock parser for testing."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        return path.suffix == ".mock"

    def parse(self, path: Path) -> ParsedDocument:
        return ParsedDocument(
            name=path.name,
            content="mock content",
            format="mock",
            metadata={},
            char_count=12,
            parse_warnings=[],
        )


def test_register_and_find_parser():
    """Registry finds registered parser for matching file."""
    registry = ParserRegistry()
    registry.register(MockParser())
    parser = registry.find_parser(Path("test.mock"))
    assert parser is not None


def test_find_parser_returns_none_when_no_match():
    """Registry returns None when no parser matches."""
    registry = ParserRegistry()
    registry.register(MockParser())
    parser = registry.find_parser(Path("test.unknown"))
    assert parser is None
