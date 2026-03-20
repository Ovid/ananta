"""Document parsers for Ananta."""

from ananta.parser.base import DocumentParser
from ananta.parser.code import CodeParser
from ananta.parser.fallback import FallbackTextParser
from ananta.parser.html import HtmlParser
from ananta.parser.office import DocxParser
from ananta.parser.pdf import PdfParser
from ananta.parser.registry import ParserRegistry
from ananta.parser.text import TextParser


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
