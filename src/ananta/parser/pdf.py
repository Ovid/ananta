"""PDF parser using pdfplumber."""

from pathlib import Path

import pdfplumber

from shesha.models import ParsedDocument


class PdfParser:
    """Parser for PDF files using pdfplumber."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        return path.suffix.lower() == ".pdf"

    def parse(
        self,
        path: Path,
        include_line_numbers: bool = False,
        file_path: str | None = None,
    ) -> ParsedDocument:
        """Parse a PDF file and return a ParsedDocument.

        Args:
            path: Path to the file to parse.
            include_line_numbers: Ignored for PDF files.
            file_path: Ignored for PDF files.
        """
        warnings: list[str] = []
        pages_text: list[str] = []

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(f"--- Page {page_num} ---\n{text}")
                else:
                    warnings.append(f"Page {page_num} has no extractable text")

        content = "\n\n".join(pages_text)

        return ParsedDocument(
            name=path.name,
            content=content,
            format="pdf",
            metadata={"page_count": page_count},
            char_count=len(content),
            parse_warnings=warnings,
        )
