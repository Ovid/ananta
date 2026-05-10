"""Text extraction from uploaded documents.

Dispatches to format-specific extractors based on file extension.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pdfplumber
from docx import Document as DocxDocument
from openpyxl import load_workbook
from pptx import Presentation as PptxPresentation
from striprtf.striprtf import rtf_to_text

from ananta.explorers.document.config import MAX_EXTRACTED_TEXT_BYTES

# Extensions treated as plain text (read with open()).
#
# `.env` is intentionally NOT in this list (I8): files named `.env` typically
# contain API keys, DB credentials, and other secrets. A user who drops a
# project folder onto the explorer should not silently land their secrets
# in the RLM document store, where the LLM reads them and the LLM provider
# sees them. Combined with [C2], this also closes the drive-by-credential-
# exfiltration vector. If a user genuinely wants to ingest a config file,
# they can rename it to `.env.txt` or use a different non-secret extension.
_PLAIN_TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".log",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".htm",
        ".ini",
        ".cfg",
        ".toml",
        ".py",
        ".js",
        ".ts",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".rs",
        ".go",
        ".rb",
        ".sh",
        ".bat",
        ".sql",
        ".r",
        ".tex",
    }
)


_SUPPORTED_EXTENSIONS = _PLAIN_TEXT_EXTENSIONS | frozenset(
    {".pdf", ".docx", ".pptx", ".xlsx", ".rtf"}
)


def is_supported_extension(filename: str) -> bool:
    """Check if a filename has a supported extension for text extraction."""
    ext = Path(filename).suffix.lower()
    return ext in _SUPPORTED_EXTENSIONS


def _truncate_to_cap(text: str) -> str:
    """Truncate *text* to ``MAX_EXTRACTED_TEXT_BYTES`` with a marker (I3).

    Bounds in-process memory and the on-disk document store against
    decompression-bomb DoS via heavily-compressed xlsx/pptx/docx/pdf,
    and reduces attacker-controlled bytes flowing into the RLM context.
    Length is measured in characters; one char ≈ one UTF-8 byte for
    typical document text, with a small overhead for non-ASCII content.
    """
    if len(text) <= MAX_EXTRACTED_TEXT_BYTES:
        return text
    return (
        text[:MAX_EXTRACTED_TEXT_BYTES]
        + f"\n[Extracted text truncated to {MAX_EXTRACTED_TEXT_BYTES:,} of "
        f"{len(text):,} characters.]"
    )


def extract_text(path: Path, content_type: str | None = None) -> str:
    """Extract text content from a file.

    *content_type* is accepted for forward-compatibility but dispatch
    is by file extension. Raises ``ValueError`` for unsupported types
    or for corrupt/unreadable files (translated from per-library errors
    like pdfplumber's PDFSyntaxError, zipfile's BadZipFile, openpyxl's
    InvalidFileException, python-pptx's PackageNotFoundError).

    Output is capped at ``MAX_EXTRACTED_TEXT_BYTES`` characters with an
    inline truncation marker — see ``_truncate_to_cap``.
    """
    ext = path.suffix.lower()

    if ext in _PLAIN_TEXT_EXTENSIONS:
        return _truncate_to_cap(_extract_plain_text(path))
    fmt_extractors: dict[str, tuple[str, Callable[[Path], str]]] = {
        ".pdf": ("pdf", _extract_pdf),
        ".docx": ("docx", _extract_docx),
        ".pptx": ("pptx", _extract_pptx),
        ".xlsx": ("xlsx", _extract_xlsx),
        ".rtf": ("rtf", _extract_rtf),
    }
    if ext in fmt_extractors:
        fmt_name, fn = fmt_extractors[ext]
        try:
            return _truncate_to_cap(fn(path))
        except ValueError:
            raise
        except Exception as exc:
            # Per-format libraries raise their own exception types on corrupt
            # input (e.g. zipfile.BadZipFile). Translate to ValueError so the
            # API's per-file ValueError handler emits a "text extraction
            # failed" reason instead of a generic "unexpected upload error".
            msg = f"could not extract text from {fmt_name}: {exc}"
            raise ValueError(msg) from exc

    msg = f"Unsupported file type: {ext}"
    raise ValueError(msg)


def _extract_plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text)


def _extract_pptx(path: Path) -> str:
    prs = PptxPresentation(str(path))
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, 1):
        slide_texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                slide_texts.append(shape.text_frame.text)
        if slide_texts:
            parts.append(f"--- Slide {i} ---\n" + "\n".join(slide_texts))
    return "\n\n".join(parts)


def _extract_xlsx(path: Path) -> str:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        parts: list[str] = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows: list[str] = []
            for row in sheet.iter_rows():
                cells = [str(cell.value) if cell.value is not None else "" for cell in row]
                rows.append("\t".join(cells))
            parts.append(f"--- {sheet_name} ---\n" + "\n".join(rows))
        return "\n\n".join(parts)
    finally:
        wb.close()


def _extract_rtf(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return str(rtf_to_text(raw))


def get_page_count(path: Path) -> int | None:
    """Return page/sheet/slide count, or None for formats without pages."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    if ext == ".pptx":
        prs = PptxPresentation(str(path))
        return len(prs.slides)
    if ext == ".xlsx":
        wb = load_workbook(path, read_only=True)
        try:
            return len(wb.sheetnames)
        finally:
            wb.close()
    return None
