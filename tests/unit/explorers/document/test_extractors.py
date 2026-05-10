"""Tests for document text extractors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
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

    def test_dotfile_unsupported_message_includes_filename(self, tmp_path: Path) -> None:
        """``extract_text`` raises an actionable message for dotfiles.

        ``Path(".env").suffix`` returns ``""``, so a naive
        ``f"Unsupported file type: {ext}"`` produces ``"Unsupported file
        type: "`` — a useless reason for the user. The message must
        include either the filename or a fallback so the client can
        explain WHY the file was rejected.
        """
        f = tmp_path / ".env"
        f.write_text("API_KEY=secret\n")
        with pytest.raises(ValueError) as excinfo:
            extract_text(f)
        msg = str(excinfo.value)
        assert ".env" in msg or "no extension" in msg.lower()
        # Negative: the unhelpful naked-trailing-colon form must not appear.
        assert not msg.rstrip().endswith(":")

    def test_extensionless_unsupported_message_includes_filename(self, tmp_path: Path) -> None:
        """Extensionless filenames also surface an actionable reason."""
        f = tmp_path / "Makefile"
        f.write_text("all:\n\techo hi\n")
        with pytest.raises(ValueError) as excinfo:
            extract_text(f)
        msg = str(excinfo.value)
        assert "Makefile" in msg or "no extension" in msg.lower()
        assert not msg.rstrip().endswith(":")

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


class TestExtractedTextSizeCap:
    """``extract_text`` truncates oversized extractions (I3).

    50 MB upload caps don't bound *extracted* text size. A heavily-compressed
    xlsx/pptx/docx/pdf can be a few MB on disk and unpack to hundreds of MB
    of plain text — a decompression-bomb DoS reachable by any caller with
    upload access. The cap fires at the public ``extract_text`` boundary so
    every format inherits it, mirroring the ``truncate_code_output`` pattern
    in ``rlm/prompts.py``.
    """

    def test_oversized_plain_text_is_truncated(self, tmp_path: Path) -> None:
        from ananta.explorers.document.config import MAX_EXTRACTED_TEXT_BYTES

        f = tmp_path / "big.txt"
        # Write something a generous bit larger than the cap; the truncation
        # marker contributes a few extra bytes so we don't pin to == cap.
        f.write_text("a" * (MAX_EXTRACTED_TEXT_BYTES + 5_000))
        result = extract_text(f)
        assert len(result) <= MAX_EXTRACTED_TEXT_BYTES + 256
        assert result.startswith("a" * 100)
        assert "truncated" in result.lower()

    def test_under_cap_returned_unchanged(self, tmp_path: Path) -> None:
        from ananta.explorers.document.config import MAX_EXTRACTED_TEXT_BYTES

        f = tmp_path / "small.txt"
        # Use a value comfortably under the cap so the test is fast even with
        # a high cap.
        body = "hello world\n" * 100
        assert len(body) < MAX_EXTRACTED_TEXT_BYTES
        f.write_text(body)
        assert extract_text(f) == body

    def test_oversized_pdf_is_truncated(self, tmp_path: Path) -> None:
        """PDF extractor inherits the cap via the ``extract_text`` boundary."""
        from ananta.explorers.document.config import MAX_EXTRACTED_TEXT_BYTES

        # Simulate a parser that returns hundreds of MB of text.
        big_text = "x" * (MAX_EXTRACTED_TEXT_BYTES + 1024)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = big_text
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "big.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        with patch("ananta.explorers.document.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            result = extract_text(f)
        assert len(result) <= MAX_EXTRACTED_TEXT_BYTES + 256
        assert "truncated" in result.lower()

    def test_cap_is_bytes_not_characters_for_multibyte_text(self, tmp_path: Path) -> None:
        """Cap is enforced in UTF-8 bytes, not characters.

        The constant is named ``MAX_EXTRACTED_TEXT_BYTES`` and the config
        docstring describes a byte cap (decompression-bomb defence). For
        non-ASCII content, character count != byte count: 'é' is 2 bytes,
        '中' is 3 bytes. A character-based slice for a body of 2-byte chars
        would let through 2x the advertised cap. This test pins the byte
        semantics by patching the cap small and writing multi-byte content
        whose char count is under the cap but byte count is well over it.
        """
        from ananta.explorers.document import extractors as ext_mod

        f = tmp_path / "multibyte.txt"
        # 'é' is 2 bytes in UTF-8. 1000 chars = 2000 bytes.
        body = "é" * 1000
        f.write_text(body, encoding="utf-8")

        with patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 1000):
            result = extract_text(f)

        # The body content must be truncated to at most 1000 bytes; allow
        # a small marker overhead for the truncation message.
        assert len(result.encode("utf-8")) <= 1000 + 256
        assert "truncated" in result.lower()

    def test_pdf_streams_and_stops_after_cap_reached(self, tmp_path: Path) -> None:
        """``_extract_pdf`` stops iterating pages once the cap is reached.

        I1 (full): the 16 MiB cap previously fired on the joined string AFTER
        every page was read into memory. A heavily-compressed PDF could
        therefore decompress hundreds of MB into RAM before the truncator
        bounded it. The fix tracks cumulative bytes inside the per-page
        loop and bails as soon as the cap is crossed, so peak memory is
        bounded too — not just the on-disk store.
        """
        from ananta.explorers.document import extractors as ext_mod

        # 100 pages × 1 MB-ish each = 100 MB if naive. With cap=5 MB the
        # streaming loop should bail after ~5-6 pages — extract_text on the
        # later pages must not be called.
        pages = []
        for _ in range(100):
            p = MagicMock()
            p.extract_text.return_value = "x" * (1024 * 1024)
            pages.append(p)
        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "big.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 5 * 1024 * 1024),
            patch("ananta.explorers.document.extractors.pdfplumber") as mock_plumber,
        ):
            mock_plumber.open.return_value = mock_pdf
            extract_text(f)

        # Streaming bail: only the first ~6 pages should have been read.
        # Without the fix all 100 pages get extract_text called.
        called = sum(1 for p in pages if p.extract_text.called)
        assert called < 20, f"streaming should bail early, but {called} pages were read"

    def test_docx_streams_and_stops_after_cap_reached(self, tmp_path: Path) -> None:
        """``_extract_docx`` stops iterating paragraphs once the cap is reached.

        Counts how many paragraphs were yielded by the source iterator —
        without streaming, all 100 are consumed and ~100 MB is built in
        Python memory before the cap fires at the public boundary.
        """
        from ananta.explorers.document import extractors as ext_mod

        consumed: list[int] = [0]

        def para_gen() -> Iterator[Any]:
            for _ in range(100):
                consumed[0] += 1
                p = MagicMock()
                p.text = "x" * (1024 * 1024)
                yield p

        mock_doc = MagicMock()
        mock_doc.paragraphs = para_gen()

        f = tmp_path / "big.docx"
        f.write_bytes(b"PK fake docx")

        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 5 * 1024 * 1024),
            patch("ananta.explorers.document.extractors.DocxDocument") as mock_cls,
        ):
            mock_cls.return_value = mock_doc
            extract_text(f)

        assert consumed[0] < 20, (
            f"streaming should bail early, but {consumed[0]} paragraphs were consumed"
        )

    def test_pptx_streams_and_stops_after_cap_reached(self, tmp_path: Path) -> None:
        """``_extract_pptx`` stops iterating slides once the cap is reached."""
        from ananta.explorers.document import extractors as ext_mod

        consumed: list[int] = [0]

        def slide_gen() -> Iterator[Any]:
            for _ in range(100):
                consumed[0] += 1
                shape = MagicMock()
                shape.has_text_frame = True
                shape.text_frame.text = "x" * (1024 * 1024)
                slide = MagicMock()
                slide.shapes = [shape]
                yield slide

        mock_prs = MagicMock()
        mock_prs.slides = slide_gen()

        f = tmp_path / "big.pptx"
        f.write_bytes(b"PK fake pptx")

        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 5 * 1024 * 1024),
            patch("ananta.explorers.document.extractors.PptxPresentation") as mock_cls,
        ):
            mock_cls.return_value = mock_prs
            extract_text(f)

        assert consumed[0] < 20, (
            f"streaming should bail early, but {consumed[0]} slides were consumed"
        )

    def test_xlsx_streams_and_stops_after_cap_reached(self, tmp_path: Path) -> None:
        """``_extract_xlsx`` stops iterating sheets/rows once the cap is reached."""
        from ananta.explorers.document import extractors as ext_mod

        consumed: list[int] = [0]

        def row_gen() -> Iterator[Any]:
            for _ in range(100):
                consumed[0] += 1
                cell = MagicMock()
                cell.value = "x" * (1024 * 1024)
                yield [cell]

        mock_sheet = MagicMock()
        mock_sheet.iter_rows.return_value = row_gen()
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_sheet

        f = tmp_path / "big.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 5 * 1024 * 1024),
            patch("ananta.explorers.document.extractors.load_workbook") as mock_load,
        ):
            mock_load.return_value = mock_wb
            extract_text(f)

        assert consumed[0] < 20, (
            f"streaming should bail early, but {consumed[0]} rows were consumed"
        )

    def test_pptx_bails_inside_a_slide_with_many_shapes(self, tmp_path: Path) -> None:
        """``_extract_pptx`` must bail out *inside* a single slide when its
        cumulative shape text exceeds the cap (S3).

        Same class as I6 (xlsx). The previous implementation accumulated
        every shape's text frame on a slide before the per-slide cap check
        fired, so a slide with thousands of shapes could allocate large
        in-memory strings before the cap had a chance to interrupt.
        """
        from ananta.explorers.document import extractors as ext_mod

        shapes_consumed: list[int] = [0]

        def shape_gen() -> Iterator[Any]:
            # 5,000 shapes of ~1 KiB each = ~5 MiB of in-memory strings if
            # naively materialised. With a 100 KiB cap, only ~100 shapes
            # are needed to trip the cap.
            for _ in range(5_000):
                shapes_consumed[0] += 1
                shape = MagicMock()
                shape.has_text_frame = True
                shape.text_frame.text = "x" * 1024
                yield shape

        # A SINGLE slide that contains many shapes.
        mock_slide = MagicMock()
        mock_slide.shapes = shape_gen()
        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        f = tmp_path / "single-slide-bomb.pptx"
        f.write_bytes(b"PK fake pptx")

        cap = 100 * 1024  # 100 KiB
        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", cap),
            patch("ananta.explorers.document.extractors.PptxPresentation") as mock_pptx,
        ):
            mock_pptx.return_value = mock_prs
            extract_text(f)

        assert shapes_consumed[0] < 1000, (
            f"streaming should bail inside the slide, but {shapes_consumed[0]} "
            "shapes were consumed before the cap fired"
        )

    def test_xlsx_bails_inside_a_single_row_with_many_cells(self, tmp_path: Path) -> None:
        """``_extract_xlsx`` must bail out *inside* a single row when its
        cumulative cells exceed the cap (I6).

        The previous implementation materialised every cell in a row via a
        single list comprehension before any cap check fired. A maliciously
        crafted single-row workbook with millions of populated cells could
        therefore allocate hundreds of MB of Python strings before
        ``_truncate_to_cap`` ran. The 50 MiB upload cap doesn't bound the
        in-memory expansion: ``read_only=True`` iterates lazily by row, but
        the per-row list comprehension realises all cells at once.

        Sheet structure for this test: a SINGLE row containing many cells.
        With a small cap, the per-cell counter must trigger a break inside
        the row before all cells are consumed.
        """
        from ananta.explorers.document import extractors as ext_mod

        cells_consumed: list[int] = [0]

        def cell_gen() -> Iterator[Any]:
            # 10,000 cells of 1 KiB each = ~10 MiB of in-memory string data
            # if naively materialised. With a 100 KiB cap the cap should
            # fire inside the row well before all cells are visited.
            for _ in range(10_000):
                cells_consumed[0] += 1
                cell = MagicMock()
                cell.value = "x" * 1024
                yield cell

        # Single-row sheet: iter_rows yields ONE row, but that row has
        # thousands of cells. Iteration over the row triggers cell_gen.
        def row_gen() -> Iterator[Any]:
            yield cell_gen()

        mock_sheet = MagicMock()
        mock_sheet.iter_rows.return_value = row_gen()
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_sheet

        f = tmp_path / "single-row-bomb.xlsx"
        f.write_bytes(b"PK fake xlsx")

        cap = 100 * 1024  # 100 KiB
        with (
            patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", cap),
            patch("ananta.explorers.document.extractors.load_workbook") as mock_load,
        ):
            mock_load.return_value = mock_wb
            extract_text(f)

        # Cell counter should be well under the 10,000 total. With a 100 KiB
        # cap and 1 KiB cells, ~100 cells suffice to hit the cap; allow
        # headroom for the tab-separator counter and per-row overhead.
        assert cells_consumed[0] < 1000, (
            f"streaming should bail inside the row, but {cells_consumed[0]} "
            "cells were consumed before the cap fired"
        )

    def test_truncation_does_not_split_multibyte_character(self, tmp_path: Path) -> None:
        """Boundary slice must not split a multi-byte UTF-8 sequence.

        Slicing bytes mid-character would produce a string containing a
        replacement char or fail to decode; the result must remain valid
        UTF-8 with no replacement characters introduced by the truncation.
        """
        from ananta.explorers.document import extractors as ext_mod

        f = tmp_path / "boundary.txt"
        # 3-byte char '中' x 1000 = 3000 bytes. With cap=1000, the boundary
        # slice falls on a 3-byte boundary if naive — proving it doesn't
        # produce a U+FFFD replacement character.
        body = "中" * 1000
        f.write_text(body, encoding="utf-8")

        with patch.object(ext_mod, "MAX_EXTRACTED_TEXT_BYTES", 1000):
            result = extract_text(f)

        # No U+FFFD replacement character should appear in the body portion;
        # we strip the marker and assert the body is clean.
        body_part = result.split("\n[Extracted text truncated")[0]
        assert "�" not in body_part


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

    def test_rtf_with_cp1252_bytes_does_not_replace_to_fffd(self, tmp_path: Path) -> None:
        """RTF files commonly include raw 8-bit bytes (CP1252 / Windows-1252)
        in legacy Word output (S1). Reading them as UTF-8 with errors="replace"
        substituted U+FFFD for every non-ASCII byte before striprtf could
        decode it, producing silent data loss on legitimate RTF uploads.

        Read as cp1252 so each 8-bit byte round-trips to its expected
        Unicode code point. The actual non-ASCII characters in standard
        RTF come from the ``\\'XX`` escape codes that striprtf decodes,
        but raw 8-bit bytes appear in real-world RTFs too.
        """
        f = tmp_path / "doc.rtf"
        # 0x93 / 0x94 are CP1252 left/right double quotation marks. In
        # UTF-8 they're invalid leading bytes — replace=replace would
        # produce U+FFFD. The pass-through behaviour we want is that the
        # raw bytes round-trip into the string given to rtf_to_text.
        raw_bytes = b"{\\rtf1 \x93Hello\x94 RTF}"
        f.write_bytes(raw_bytes)

        captured: list[str] = []

        def capture_rtf(source: str) -> str:
            captured.append(source)
            return source

        with patch(
            "ananta.explorers.document.extractors.rtf_to_text",
            side_effect=capture_rtf,
        ):
            extract_text(f)

        assert captured, "rtf_to_text was not called"
        # The 0x93/0x94 bytes must round-trip — no replacement chars.
        assert "�" not in captured[0], (
            "Reading RTF as utf-8 substituted U+FFFD for legitimate CP1252 bytes"
        )


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
