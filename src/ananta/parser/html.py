"""HTML parser using BeautifulSoup."""

from pathlib import Path

from bs4 import BeautifulSoup

from shesha.models import ParsedDocument


class HtmlParser:
    """Parser for HTML files using BeautifulSoup."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        return path.suffix.lower() in {".html", ".htm"}

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse an HTML file and return a ParsedDocument.

        Args:
            path: Path to the file to parse.
            include_line_numbers: Ignored for HTML files.
            file_path: Ignored for HTML files.
        """
        raw_html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(raw_html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "meta", "link"]):
            element.decompose()

        # Extract text with some structure preserved
        text = soup.get_text(separator="\n", strip=True)

        # Extract title if present
        title = soup.title.string if soup.title else None

        return ParsedDocument(
            name=path.name,
            content=text,
            format="html",
            metadata={"title": title} if title else {},
            char_count=len(text),
            parse_warnings=[],
        )
