"""Tests for document text extractors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ananta.explorers.document.extractors import extract_text, get_page_count


class TestPlainTextExtraction:
    """Tests for plain text file extraction."""

    def test_extracts_txt_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("Hello, world!")
        assert extract_text(f) == "Hello, world!"

    def test_extracts_md_file(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Title\nBody text")
        assert extract_text(f) == "# Title\nBody text"

    def test_extracts_csv_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2")
        assert extract_text(f) == "a,b\n1,2"

    def test_extracts_json_file(self, tmp_path: Path) -> None:
        f = tmp_path / "config.json"
        f.write_text('{"key": "value"}')
        assert extract_text(f) == '{"key": "value"}'

    def test_extracts_yaml_file(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        assert extract_text(f) == "key: value"

    def test_extracts_xml_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xml"
        f.write_text("<root>hello</root>")
        assert extract_text(f) == "<root>hello</root>"

    def test_extracts_html_file(self, tmp_path: Path) -> None:
        f = tmp_path / "page.html"
        f.write_text("<html><body>hi</body></html>")
        assert extract_text(f) == "<html><body>hi</body></html>"

    def test_extracts_log_file(self, tmp_path: Path) -> None:
        f = tmp_path / "app.log"
        f.write_text("2026-01-01 INFO started")
        assert extract_text(f) == "2026-01-01 INFO started"

    def test_content_type_parameter_accepted(self, tmp_path: Path) -> None:
        """extract_text accepts an optional content_type parameter."""
        f = tmp_path / "data.txt"
        f.write_text("hello")
        assert extract_text(f, content_type="text/plain") == "hello"


class TestUnsupportedExtension:
    """Tests for unsupported file types."""

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG")
        with pytest.raises(ValueError, match="[Uu]nsupported"):
            extract_text(f)

    def test_env_file_is_unsupported(self, tmp_path: Path) -> None:
        """`.env` files must NOT be accepted (I8).

        `.env` typically holds API keys, DB credentials, and other secrets.
        A user dropping a project folder onto the explorer should not silently
        land their secrets into the RLM document store, where the LLM reads
        them and the LLM provider sees them. Combined with [C2] this also
        closes the drive-by credential-exfiltration vector.
        """
        from ananta.explorers.document.extractors import is_supported_extension

        f = tmp_path / ".env"
        f.write_text("API_KEY=secret\n")
        assert is_supported_extension(".env") is False
        with pytest.raises(ValueError, match="[Uu]nsupported"):
            extract_text(f)


class TestCorruptFileTranslation:
    """Per-format parser exceptions must be translated to ValueError (I5).

    Reproduces I5: pdfplumber, python-docx, python-pptx, openpyxl etc. raise
    library-specific exceptions on malformed input (PDFSyntaxError,
    BadZipFile, InvalidFileException, PackageNotFoundError, ...) — none
    subclass ValueError. Without translation, the API's `except ValueError`
    misses them and the user sees the generic "unexpected upload error".
    """

    def test_corrupt_pdf_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.pdf"
        f.write_bytes(b"not a pdf")
        with pytest.raises(ValueError):
            extract_text(f)

    def test_corrupt_docx_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.docx"
        f.write_bytes(b"not a docx")
        with pytest.raises(ValueError):
            extract_text(f)

    def test_corrupt_pptx_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.pptx"
        f.write_bytes(b"not a pptx")
        with pytest.raises(ValueError):
            extract_text(f)

    def test_corrupt_xlsx_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.xlsx"
        f.write_bytes(b"not an xlsx")
        with pytest.raises(ValueError):
            extract_text(f)


class TestPdfExtraction:
    """Tests for PDF text extraction."""

    def test_extracts_pdf(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with patch("ananta.explorers.document.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            result = extract_text(f)

        assert result == "Page 1 content"

    def test_pdf_multiple_pages(self, tmp_path: Path) -> None:
        pages = []
        for i in range(3):
            p = MagicMock()
            p.extract_text.return_value = f"Page {i + 1}"
            pages.append(p)
        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "multi.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with patch("ananta.explorers.document.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            result = extract_text(f)

        assert "Page 1" in result
        assert "Page 3" in result


class TestDocxExtraction:
    """Tests for Word .docx extraction."""

    def test_extracts_docx(self, tmp_path: Path) -> None:
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        f = tmp_path / "report.docx"
        f.write_bytes(b"PK fake docx")

        with patch("ananta.explorers.document.extractors.DocxDocument") as mock_cls:
            mock_cls.return_value = mock_doc
            result = extract_text(f)

        assert "First paragraph" in result
        assert "Second paragraph" in result


class TestPptxExtraction:
    """Tests for PowerPoint .pptx extraction."""

    def test_extracts_pptx(self, tmp_path: Path) -> None:
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame.text = "Slide content"
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        f = tmp_path / "deck.pptx"
        f.write_bytes(b"PK fake pptx")

        with patch("ananta.explorers.document.extractors.PptxPresentation") as mock_cls:
            mock_cls.return_value = mock_prs
            result = extract_text(f)

        assert "Slide content" in result


class TestXlsxExtraction:
    """Tests for Excel .xlsx extraction."""

    def test_extracts_xlsx(self, tmp_path: Path) -> None:
        mock_sheet = MagicMock()
        mock_sheet.title = "Sheet1"
        mock_sheet.iter_rows.return_value = [
            [MagicMock(value="A1"), MagicMock(value="B1")],
            [MagicMock(value="A2"), MagicMock(value=42)],
        ]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_sheet

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("ananta.explorers.document.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            result = extract_text(f)

        assert "Sheet1" in result
        assert "A1" in result

    def test_xlsx_workbook_is_closed(self, tmp_path: Path) -> None:
        mock_sheet = MagicMock()
        mock_sheet.iter_rows.return_value = []
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_sheet

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("ananta.explorers.document.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            extract_text(f)

        mock_wb.close.assert_called_once()


class TestRtfExtraction:
    """Tests for RTF extraction."""

    def test_extracts_rtf(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.rtf"
        f.write_text(r"{\rtf1 Hello RTF}")

        with patch("ananta.explorers.document.extractors.rtf_to_text") as mock_rtf:
            mock_rtf.return_value = "Hello RTF"
            result = extract_text(f)

        assert result == "Hello RTF"


class TestGetPageCount:
    """Tests for page/sheet/slide count extraction."""

    def test_pdf_page_count(self, tmp_path: Path) -> None:
        mock_pdf = MagicMock()
        mock_pdf.pages = [MagicMock(), MagicMock(), MagicMock()]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with patch("ananta.explorers.document.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            assert get_page_count(f) == 3

    def test_pptx_slide_count(self, tmp_path: Path) -> None:
        mock_prs = MagicMock()
        mock_prs.slides = [MagicMock(), MagicMock()]

        f = tmp_path / "deck.pptx"
        f.write_bytes(b"PK fake pptx")

        with patch("ananta.explorers.document.extractors.PptxPresentation") as mock_cls:
            mock_cls.return_value = mock_prs
            assert get_page_count(f) == 2

    def test_xlsx_sheet_count(self, tmp_path: Path) -> None:
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1", "Sheet2", "Sheet3"]

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("ananta.explorers.document.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            assert get_page_count(f) == 3

    def test_xlsx_page_count_closes_workbook(self, tmp_path: Path) -> None:
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("ananta.explorers.document.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            get_page_count(f)

        mock_wb.close.assert_called_once()

    def test_plain_text_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        assert get_page_count(f) is None

    def test_unsupported_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG")
        assert get_page_count(f) is None
