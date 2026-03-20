"""Tests for Office document parser."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ananta.parser.office import DocxParser


@pytest.fixture
def parser() -> DocxParser:
    return DocxParser()


class TestDocxParser:
    """Tests for DocxParser."""

    def test_can_parse_docx(self, parser: DocxParser):
        """DocxParser can parse .docx files."""
        assert parser.can_parse(Path("document.docx"))

    def test_cannot_parse_other(self, parser: DocxParser):
        """DocxParser cannot parse non-docx files."""
        assert not parser.can_parse(Path("document.doc"))  # Old format not supported
        assert not parser.can_parse(Path("document.pdf"))

    @patch("ananta.parser.office.Document")
    def test_parse_docx_extracts_paragraphs(self, mock_document_cls: MagicMock, parser: DocxParser):
        """DocxParser extracts paragraphs from document."""
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.tables = []
        mock_document_cls.return_value = mock_doc

        doc = parser.parse(Path("test.docx"))
        assert doc.name == "test.docx"
        assert "First paragraph" in doc.content
        assert "Second paragraph" in doc.content
        assert doc.format == "docx"
