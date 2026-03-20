"""Tests for PDF parser."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ananta.parser.pdf import PdfParser


@pytest.fixture
def parser() -> PdfParser:
    return PdfParser()


class TestPdfParser:
    """Tests for PdfParser."""

    def test_can_parse_pdf(self, parser: PdfParser):
        """PdfParser can parse .pdf files."""
        assert parser.can_parse(Path("document.pdf"))

    def test_cannot_parse_other(self, parser: PdfParser):
        """PdfParser cannot parse non-PDF files."""
        assert not parser.can_parse(Path("document.txt"))
        assert not parser.can_parse(Path("document.docx"))

    @patch("ananta.parser.pdf.pdfplumber")
    def test_parse_pdf_extracts_text(self, mock_pdfplumber: MagicMock, parser: PdfParser):
        """PdfParser extracts text from PDF pages."""
        # Mock PDF page
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content"

        # Mock PDF object
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = lambda *args: None
        mock_pdfplumber.open.return_value = mock_pdf

        doc = parser.parse(Path("test.pdf"))
        assert doc.name == "test.pdf"
        assert "Page 1 content" in doc.content
        assert doc.format == "pdf"
        assert doc.metadata["page_count"] == 1
