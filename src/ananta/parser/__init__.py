"""Document parsers for Shesha."""

from shesha.parser.base import DocumentParser
from shesha.parser.code import CodeParser
from shesha.parser.fallback import FallbackTextParser
from shesha.parser.html import HtmlParser
from shesha.parser.office import DocxParser
from shesha.parser.pdf import PdfParser
from shesha.parser.registry import ParserRegistry
from shesha.parser.text import TextParser


def create_default_registry() -> ParserRegistry:
    """Create a parser registry with all default parsers."""
    registry = ParserRegistry()
    # Order matters: more specific parsers first, fallback last
    registry.register(PdfParser())
    registry.register(DocxParser())
    registry.register(HtmlParser())
    registry.register(CodeParser())
    registry.register(TextParser())
    registry.register(FallbackTextParser())  # Catch-all for any text file
    return registry


__all__ = [
    "DocumentParser",
    "ParserRegistry",
    "TextParser",
    "CodeParser",
    "PdfParser",
    "HtmlParser",
    "DocxParser",
    "FallbackTextParser",
    "create_default_registry",
]
