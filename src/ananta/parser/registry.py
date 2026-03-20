"""Parser registry for managing document parsers."""

from pathlib import Path

from shesha.parser.base import DocumentParser


class ParserRegistry:
    """Registry for document parsers."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        """Register a parser."""
        self._parsers.append(parser)

    def find_parser(self, path: Path, mime_type: str | None = None) -> DocumentParser | None:
        """Find a parser that can handle the given file."""
        for parser in self._parsers:
            if parser.can_parse(path, mime_type):
                return parser
        return None
