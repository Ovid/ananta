# Document Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Document Explorer POC that lets users upload files, organize them into topics, and query them via Shesha's RLM engine.

**Architecture:** Follows the Code Explorer pattern — one Shesha project per uploaded document, topics hold project_id references, FastAPI backend with custom WebSocket handler, React frontend using `@shesha/shared-ui`.

**Tech Stack:** Python 3.11+ / FastAPI / pdfplumber / python-docx / python-pptx / openpyxl / striprtf / React 19 / Tailwind CSS 4 / Vite 7

---

## Task 1: Text Extractors

**Files:**
- Create: `src/shesha/experimental/document_explorer/extractors.py`
- Test: `tests/unit/experimental/document_explorer/test_extractors.py`

**Step 1: Write failing tests for plain text extraction**

```python
# tests/unit/experimental/document_explorer/test_extractors.py
"""Tests for document text extractors."""

from __future__ import annotations

from pathlib import Path

import pytest

from shesha.experimental.document_explorer.extractors import extract_text, get_page_count


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


class TestPdfExtraction:
    """Tests for PDF text extraction."""

    def test_extracts_pdf(self, tmp_path: Path) -> None:
        """PDF extraction returns non-empty string."""
        # Create a minimal PDF using pdfplumber's test helper isn't practical,
        # so we test with a real tiny PDF created via reportlab or similar.
        # For unit tests, we mock pdfplumber.
        from unittest.mock import MagicMock, patch

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with patch("shesha.experimental.document_explorer.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            result = extract_text(f)

        assert result == "Page 1 content"

    def test_pdf_multiple_pages(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

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

        with patch("shesha.experimental.document_explorer.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            result = extract_text(f)

        assert "Page 1" in result
        assert "Page 3" in result


class TestDocxExtraction:
    """Tests for Word .docx extraction."""

    def test_extracts_docx(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        f = tmp_path / "report.docx"
        f.write_bytes(b"PK fake docx")

        with patch("shesha.experimental.document_explorer.extractors.DocxDocument") as mock_cls:
            mock_cls.return_value = mock_doc
            result = extract_text(f)

        assert "First paragraph" in result
        assert "Second paragraph" in result


class TestPptxExtraction:
    """Tests for PowerPoint .pptx extraction."""

    def test_extracts_pptx(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame.text = "Slide content"
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        f = tmp_path / "deck.pptx"
        f.write_bytes(b"PK fake pptx")

        with patch("shesha.experimental.document_explorer.extractors.PptxPresentation") as mock_cls:
            mock_cls.return_value = mock_prs
            result = extract_text(f)

        assert "Slide content" in result


class TestXlsxExtraction:
    """Tests for Excel .xlsx extraction."""

    def test_extracts_xlsx(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_sheet = MagicMock()
        mock_sheet.title = "Sheet1"
        mock_sheet.iter_rows.return_value = [
            [MagicMock(value="A1"), MagicMock(value="B1")],
            [MagicMock(value="A2"), MagicMock(value=42)],
        ]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = lambda self, key: mock_sheet

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("shesha.experimental.document_explorer.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            result = extract_text(f)

        assert "Sheet1" in result
        assert "A1" in result


class TestRtfExtraction:
    """Tests for RTF extraction."""

    def test_extracts_rtf(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        f = tmp_path / "doc.rtf"
        f.write_text(r"{\rtf1 Hello RTF}")

        with patch("shesha.experimental.document_explorer.extractors.rtf_to_text") as mock_rtf:
            mock_rtf.return_value = "Hello RTF"
            result = extract_text(f)

        assert result == "Hello RTF"


class TestGetPageCount:
    """Tests for page/sheet/slide count extraction."""

    def test_pdf_page_count(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_pdf = MagicMock()
        mock_pdf.pages = [MagicMock(), MagicMock(), MagicMock()]
        mock_pdf.__enter__ = lambda self: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        with patch("shesha.experimental.document_explorer.extractors.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            assert get_page_count(f) == 3

    def test_pptx_slide_count(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_prs = MagicMock()
        mock_prs.slides = [MagicMock(), MagicMock()]

        f = tmp_path / "deck.pptx"
        f.write_bytes(b"PK fake pptx")

        with patch("shesha.experimental.document_explorer.extractors.PptxPresentation") as mock_cls:
            mock_cls.return_value = mock_prs
            assert get_page_count(f) == 2

    def test_xlsx_sheet_count(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1", "Sheet2", "Sheet3"]

        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK fake xlsx")

        with patch("shesha.experimental.document_explorer.extractors.load_workbook") as mock_load:
            mock_load.return_value = mock_wb
            assert get_page_count(f) == 3

    def test_plain_text_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        assert get_page_count(f) is None

    def test_unsupported_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG")
        assert get_page_count(f) is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/experimental/document_explorer/test_extractors.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/shesha/experimental/document_explorer/__init__.py
```

```python
# src/shesha/experimental/document_explorer/extractors.py
"""Text extraction from uploaded documents.

Dispatches to format-specific extractors based on file extension.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from docx import Document as DocxDocument
from openpyxl import load_workbook
from pptx import Presentation as PptxPresentation
from striprtf.striprtf import rtf_to_text

# Extensions treated as plain text (read with open())
_PLAIN_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".ini", ".cfg", ".toml", ".env",
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".rs",
    ".go", ".rb", ".sh", ".bat", ".sql", ".r", ".tex",
})


def extract_text(path: Path, content_type: str | None = None) -> str:
    """Extract text content from a file.

    *content_type* is accepted for forward-compatibility but dispatch
    is by file extension.  Raises ``ValueError`` for unsupported types.
    """
    ext = path.suffix.lower()

    if ext in _PLAIN_TEXT_EXTENSIONS:
        return _extract_plain_text(path)
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".pptx":
        return _extract_pptx(path)
    if ext == ".xlsx":
        return _extract_xlsx(path)
    if ext == ".rtf":
        return _extract_rtf(path)

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
    doc = DocxDocument(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text)


def _extract_pptx(path: Path) -> str:
    prs = PptxPresentation(path)
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
    parts: list[str] = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows: list[str] = []
        for row in sheet.iter_rows():
            cells = [str(cell.value) if cell.value is not None else "" for cell in row]
            rows.append("\t".join(cells))
        parts.append(f"--- {sheet_name} ---\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _extract_rtf(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return rtf_to_text(raw)


def get_page_count(path: Path) -> int | None:
    """Return page/sheet/slide count, or None for formats without pages."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    if ext == ".pptx":
        prs = PptxPresentation(path)
        return len(prs.slides)
    if ext == ".xlsx":
        wb = load_workbook(path, read_only=True)
        return len(wb.sheetnames)
    return None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/experimental/document_explorer/test_extractors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/__init__.py \
        src/shesha/experimental/document_explorer/extractors.py \
        tests/unit/experimental/document_explorer/__init__.py \
        tests/unit/experimental/document_explorer/test_extractors.py
git commit -m "feat(document-explorer): add text extractors with TDD"
```

---

## Task 2: DocumentTopicManager

**Files:**
- Create: `src/shesha/experimental/document_explorer/topics.py`
- Test: `tests/unit/experimental/document_explorer/test_topics.py`

**Step 1: Write failing tests**

Mirror `tests/unit/experimental/code_explorer/test_topics.py` but rename `repos` → `docs` throughout. The key classes:

```python
# tests/unit/experimental/document_explorer/test_topics.py
"""Tests for DocumentTopicManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shesha.experimental.document_explorer.topics import DocumentTopicManager


class TestCreateAndListTopics:
    def test_create_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        assert "Reports" in mgr.list_topics()

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        assert mgr.list_topics() == []

    def test_list_topics_multiple(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Contracts")
        mgr.create("Research")
        assert sorted(mgr.list_topics()) == ["Contracts", "Reports", "Research"]

    def test_topic_json_metadata(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("My Docs")
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        meta = json.loads((dirs[0] / "topic.json").read_text())
        assert meta["name"] == "My Docs"
        assert meta["docs"] == []

    def test_create_duplicate_is_idempotent(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Reports")
        assert mgr.list_topics().count("Reports") == 1

    @pytest.mark.parametrize("name", ["!!!", "   ", "---", ""])
    def test_create_rejects_empty_slug(self, tmp_path: Path, name: str) -> None:
        mgr = DocumentTopicManager(tmp_path)
        with pytest.raises(ValueError, match="[Ee]mpty"):
            mgr.create(name)


class TestAddAndListDocs:
    def test_add_doc_to_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "quarterly-report-a3f2")
        assert mgr.list_docs("Reports") == ["quarterly-report-a3f2"]

    def test_add_multiple_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-2")
        assert sorted(mgr.list_docs("Reports")) == ["doc-1", "doc-2"]

    def test_list_docs_empty_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.list_docs("Empty") == []

    def test_add_duplicate_doc_is_idempotent(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-1")
        assert mgr.list_docs("Reports") == ["doc-1"]

    def test_add_doc_to_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.add_doc("Nonexistent", "doc-1")


class TestRemoveDoc:
    def test_remove_doc_from_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-2")
        mgr.remove_doc("Reports", "doc-1")
        assert mgr.list_docs("Reports") == ["doc-2"]

    def test_remove_nonexistent_doc_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        with pytest.raises(ValueError, match="Doc not found"):
            mgr.remove_doc("Reports", "nonexistent")


class TestSameDocMultipleTopics:
    def test_same_doc_in_multiple_topics(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Research")
        mgr.add_doc("Reports", "shared-doc")
        mgr.add_doc("Research", "shared-doc")
        assert "shared-doc" in mgr.list_docs("Reports")
        assert "shared-doc" in mgr.list_docs("Research")


class TestListAllDocs:
    def test_list_all_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "doc-1")
        mgr.add_doc("A", "doc-2")
        mgr.add_doc("B", "doc-2")
        mgr.add_doc("B", "doc-3")
        assert sorted(mgr.list_all_docs()) == ["doc-1", "doc-2", "doc-3"]

    def test_list_all_docs_no_duplicates(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        assert mgr.list_all_docs() == ["shared"]


class TestUncategorizedDocs:
    def test_list_uncategorized_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.add_doc("A", "doc-1")
        uncategorized = mgr.list_uncategorized_docs(["doc-1", "doc-2", "doc-3"])
        assert sorted(uncategorized) == ["doc-2", "doc-3"]


class TestDeleteTopic:
    def test_delete_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("ToDelete")
        mgr.delete("ToDelete")
        assert mgr.list_topics() == []


class TestFindTopicsForDoc:
    def test_find_topics_for_doc(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        assert sorted(mgr.find_topics_for_doc("shared")) == ["A", "B"]


class TestRemoveDocFromAll:
    def test_remove_doc_from_all(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        mgr.add_doc("B", "other")
        mgr.remove_doc_from_all("shared")
        assert mgr.list_docs("A") == []
        assert mgr.list_docs("B") == ["other"]


class TestRenameTopic:
    def test_rename_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Old")
        mgr.add_doc("Old", "doc-1")
        mgr.rename("Old", "New")
        assert "New" in mgr.list_topics()
        assert "Old" not in mgr.list_topics()
        assert mgr.list_docs("New") == ["doc-1"]

    def test_rename_to_existing_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.create("Beta")
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("Alpha", "Beta")
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/experimental/document_explorer/test_topics.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Copy `src/shesha/experimental/code_explorer/topics.py` and rename:
- Class: `CodeExplorerTopicManager` → `DocumentTopicManager`
- `_TopicMeta.repos` → `_TopicMeta.docs`
- All method names: `add_repo` → `add_doc`, `remove_repo` → `remove_doc`, `list_repos` → `list_docs`, `list_all_repos` → `list_all_docs`, `list_uncategorized_repos` → `list_uncategorized_docs`, `find_topics_for_repo` → `find_topics_for_doc`, `remove_repo_from_all` → `remove_doc_from_all`
- Error messages: "Repo not found" → "Doc not found"

```python
# src/shesha/experimental/document_explorer/topics.py
"""Topic management for the document explorer.

Topics are lightweight reference containers that hold project_id strings
pointing to uploaded documents. A document can appear in zero or more topics.
Deleting a topic removes the references but not the documents themselves.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TypedDict

TOPIC_META_FILE = "topic.json"


class _TopicMeta(TypedDict):
    name: str
    docs: list[str]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class DocumentTopicManager:
    """Manages topics as lightweight reference containers for documents."""

    def __init__(self, topics_dir: Path) -> None:
        self._topics_dir = topics_dir
        self._topics_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str) -> None:
        slug = _slugify(name)
        if not slug:
            msg = f"Topic name produces an empty slug: {name!r}"
            raise ValueError(msg)
        topic_dir = self._topics_dir / slug
        meta_path = topic_dir / TOPIC_META_FILE
        if meta_path.exists():
            return
        topic_dir.mkdir(parents=True, exist_ok=True)
        meta: _TopicMeta = {"name": name, "docs": []}
        meta_path.write_text(json.dumps(meta, indent=2))

    def rename(self, old_name: str, new_name: str) -> None:
        meta, meta_path = self._resolve(old_name)
        if new_name != old_name:
            existing_names: set[str] = set()
            for d in self._iter_topic_dirs():
                m = self._read_meta(d)
                if m is not None and m["name"] != old_name:
                    existing_names.add(m["name"])
            if new_name in existing_names:
                msg = f"Topic '{new_name}' already exists"
                raise ValueError(msg)
        meta["name"] = new_name
        meta_path.write_text(json.dumps(meta, indent=2))

    def delete(self, name: str) -> None:
        _meta, meta_path = self._resolve(name)
        shutil.rmtree(meta_path.parent)

    def list_topics(self) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None and meta["name"] not in seen:
                seen.add(meta["name"])
                names.append(meta["name"])
        return sorted(names)

    def add_doc(self, topic: str, project_id: str) -> None:
        meta, meta_path = self._resolve(topic)
        docs = meta["docs"]
        if project_id not in docs:
            docs.append(project_id)
            meta_path.write_text(json.dumps(meta, indent=2))

    def remove_doc(self, topic: str, project_id: str) -> None:
        meta, meta_path = self._resolve(topic)
        docs = meta["docs"]
        if project_id not in docs:
            msg = f"Doc not found in topic '{topic}': {project_id}"
            raise ValueError(msg)
        docs.remove(project_id)
        meta_path.write_text(json.dumps(meta, indent=2))

    def list_docs(self, topic: str) -> list[str]:
        meta, _meta_path = self._resolve(topic)
        return list(meta["docs"])

    def list_all_docs(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            for doc in meta["docs"]:
                if doc not in seen:
                    seen.add(doc)
                    result.append(doc)
        return result

    def list_uncategorized_docs(self, all_project_ids: list[str]) -> list[str]:
        categorized = set(self.list_all_docs())
        return [pid for pid in all_project_ids if pid not in categorized]

    def find_topics_for_doc(self, project_id: str) -> list[str]:
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None and project_id in meta["docs"]:
                result.append(meta["name"])
        return sorted(result)

    def remove_doc_from_all(self, project_id: str) -> None:
        for topic_dir in self._iter_topic_dirs():
            meta_path = topic_dir / TOPIC_META_FILE
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            docs = meta["docs"]
            if project_id in docs:
                docs.remove(project_id)
                meta_path.write_text(json.dumps(meta, indent=2))

    def _resolve(self, name: str) -> tuple[_TopicMeta, Path]:
        for topic_dir in self._iter_topic_dirs():
            meta_path = topic_dir / TOPIC_META_FILE
            meta = self._read_meta(topic_dir)
            if meta is not None and meta["name"] == name:
                return meta, meta_path
        msg = f"Topic not found: {name}"
        raise ValueError(msg)

    def _iter_topic_dirs(self) -> list[Path]:
        if not self._topics_dir.exists():
            return []
        return sorted(
            d for d in self._topics_dir.iterdir()
            if d.is_dir() and (d / TOPIC_META_FILE).exists()
        )

    @staticmethod
    def _read_meta(topic_dir: Path) -> _TopicMeta | None:
        meta_path = topic_dir / TOPIC_META_FILE
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/experimental/document_explorer/test_topics.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/topics.py \
        tests/unit/experimental/document_explorer/test_topics.py
git commit -m "feat(document-explorer): add DocumentTopicManager with TDD"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `src/shesha/experimental/document_explorer/schemas.py`
- Test: `tests/unit/experimental/document_explorer/test_schemas.py`

**Step 1: Write failing tests**

```python
# tests/unit/experimental/document_explorer/test_schemas.py
"""Tests for document explorer Pydantic schemas."""

from __future__ import annotations

import pydantic
import pytest

from shesha.experimental.document_explorer.schemas import (
    ContextBudget,
    DocumentInfo,
    DocumentUploadResponse,
    ExchangeSchema,
    ModelInfo,
    TopicCreate,
    TopicInfo,
    TopicRename,
)


class TestDocumentInfo:
    def test_all_fields(self) -> None:
        d = DocumentInfo(
            project_id="quarterly-report-a3f2",
            filename="Quarterly Report.pdf",
            content_type="application/pdf",
            size=102400,
            upload_date="2026-03-05T12:00:00Z",
            page_count=15,
        )
        assert d.project_id == "quarterly-report-a3f2"
        assert d.filename == "Quarterly Report.pdf"
        assert d.size == 102400
        assert d.page_count == 15

    def test_page_count_nullable(self) -> None:
        d = DocumentInfo(
            project_id="notes-b1c2",
            filename="notes.txt",
            content_type="text/plain",
            size=256,
            upload_date="2026-03-05T12:00:00Z",
            page_count=None,
        )
        assert d.page_count is None

    def test_requires_fields(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            DocumentInfo(project_id="x")  # type: ignore[call-arg]


class TestDocumentUploadResponse:
    def test_all_fields(self) -> None:
        r = DocumentUploadResponse(
            project_id="doc-abc-1234",
            filename="report.pdf",
            status="created",
        )
        assert r.project_id == "doc-abc-1234"
        assert r.status == "created"


class TestReexportedSharedSchemas:
    def test_topic_create(self) -> None:
        t = TopicCreate(name="Research")
        assert t.name == "Research"

    def test_topic_rename(self) -> None:
        t = TopicRename(new_name="New Name")
        assert t.new_name == "New Name"

    def test_topic_info(self) -> None:
        t = TopicInfo(
            name="Research",
            document_count=5,
            size="",
            project_id="topic:Research",
        )
        assert t.document_count == 5

    def test_exchange_schema(self) -> None:
        e = ExchangeSchema(
            exchange_id="uuid-1",
            question="What?",
            answer="That.",
            timestamp="2026-03-05T12:00:00Z",
            tokens={"prompt": 100, "completion": 50, "total": 150},
            execution_time=5.0,
            model="test",
            document_ids=["doc-1"],
        )
        assert e.document_ids == ["doc-1"]

    def test_model_info(self) -> None:
        m = ModelInfo(model="test", max_input_tokens=128000)
        assert m.model == "test"

    def test_context_budget(self) -> None:
        b = ContextBudget(
            used_tokens=1000, max_tokens=128000, percentage=0.8, level="green"
        )
        assert b.level == "green"
```

**Step 2: Run tests — expect FAIL**

**Step 3: Write implementation**

```python
# src/shesha/experimental/document_explorer/schemas.py
"""Pydantic schemas for the document explorer API."""

from __future__ import annotations

from pydantic import BaseModel

from shesha.experimental.shared.schemas import (
    ContextBudget,
    ExchangeSchema,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)

__all__ = [
    "ContextBudget",
    "DocumentInfo",
    "DocumentUploadResponse",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
]


class DocumentInfo(BaseModel):
    project_id: str
    filename: str
    content_type: str
    size: int
    upload_date: str
    page_count: int | None


class DocumentUploadResponse(BaseModel):
    project_id: str
    filename: str
    status: str
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/schemas.py \
        tests/unit/experimental/document_explorer/test_schemas.py
git commit -m "feat(document-explorer): add Pydantic schemas with TDD"
```

---

## Task 4: Dependencies & App State

**Files:**
- Create: `src/shesha/experimental/document_explorer/dependencies.py`
- Test: `tests/unit/experimental/document_explorer/test_dependencies.py`

**Step 1: Write failing tests**

```python
# tests/unit/experimental/document_explorer/test_dependencies.py
"""Tests for DocumentExplorerState and create_app_state."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    create_app_state,
)
from shesha.experimental.document_explorer.topics import DocumentTopicManager
from shesha.experimental.shared.session import WebConversationSession


class TestDocumentExplorerState:
    def test_has_shesha(self) -> None:
        state = DocumentExplorerState(
            shesha=MagicMock(), topic_mgr=MagicMock(),
            session=MagicMock(), model="test", uploads_dir=Path("/tmp"),
        )
        assert hasattr(state, "shesha")

    def test_has_uploads_dir(self) -> None:
        state = DocumentExplorerState(
            shesha=MagicMock(), topic_mgr=MagicMock(),
            session=MagicMock(), model="test", uploads_dir=Path("/tmp/uploads"),
        )
        assert state.uploads_dir == Path("/tmp/uploads")

    def test_has_model(self) -> None:
        state = DocumentExplorerState(
            shesha=MagicMock(), topic_mgr=MagicMock(),
            session=MagicMock(), model="gpt-5", uploads_dir=Path("/tmp"),
        )
        assert state.model == "gpt-5"


class TestCreateAppState:
    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    def test_returns_state(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state, DocumentExplorerState)

    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    def test_creates_directories(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "shesha_data").is_dir()
        assert (tmp_path / "topics").is_dir()
        assert (tmp_path / "uploads").is_dir()

    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    @patch("shesha.experimental.document_explorer.dependencies.Path.home")
    def test_default_data_dir(
        self, mock_home: MagicMock, mock_shesha_cls: MagicMock, tmp_path: Path,
    ) -> None:
        mock_home.return_value = tmp_path
        state = create_app_state(data_dir=None)
        expected = tmp_path / ".shesha" / "document-explorer"
        assert (expected / "shesha_data").is_dir()
        assert (expected / "uploads").is_dir()

    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    def test_model_override(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(data_dir=tmp_path, model="custom")
        assert state.model == "custom"

    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    def test_has_topic_mgr(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.topic_mgr, DocumentTopicManager)

    @patch("shesha.experimental.document_explorer.dependencies.Shesha")
    def test_has_session(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.session, WebConversationSession)
```

**Step 2: Run tests — expect FAIL**

**Step 3: Write implementation**

```python
# src/shesha/experimental/document_explorer/dependencies.py
"""Shared state for the document explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.document_explorer.topics import DocumentTopicManager
from shesha.experimental.shared.session import WebConversationSession
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class DocumentExplorerState:
    shesha: Shesha
    topic_mgr: DocumentTopicManager
    session: WebConversationSession
    model: str
    uploads_dir: Path


def get_topic_session(
    state: DocumentExplorerState, topic_name: str,
) -> WebConversationSession:
    _meta, meta_path = state.topic_mgr._resolve(topic_name)
    topic_dir = meta_path.parent
    return WebConversationSession(topic_dir)


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> DocumentExplorerState:
    data_dir = data_dir or Path.home() / ".shesha" / "document-explorer"
    shesha_data = data_dir / "shesha_data"
    topics_dir = data_dir / "topics"
    uploads_dir = data_dir / "uploads"
    shesha_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model

    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    topic_mgr = DocumentTopicManager(topics_dir)
    session = WebConversationSession(data_dir)

    return DocumentExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model=config.model,
        uploads_dir=uploads_dir,
    )
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/dependencies.py \
        tests/unit/experimental/document_explorer/test_dependencies.py
git commit -m "feat(document-explorer): add app state and dependencies with TDD"
```

---

## Task 5: Entry Point

**Files:**
- Create: `src/shesha/experimental/document_explorer/__main__.py`
- Test: `tests/unit/experimental/document_explorer/test_main.py`

**Step 1: Write failing tests**

```python
# tests/unit/experimental/document_explorer/test_main.py
"""Tests for document explorer __main__.py entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from shesha.experimental.document_explorer.__main__ import main, parse_args


class TestParseArgs:
    def test_default_port(self) -> None:
        args = parse_args([])
        assert args.port == 8003

    def test_custom_port(self) -> None:
        args = parse_args(["--port", "9000"])
        assert args.port == 9000

    def test_default_data_dir_is_none(self) -> None:
        args = parse_args([])
        assert args.data_dir is None

    def test_no_browser_flag(self) -> None:
        args = parse_args(["--no-browser"])
        assert args.no_browser is True

    def test_default_model_is_none(self) -> None:
        args = parse_args([])
        assert args.model is None


class TestMain:
    @patch("shesha.experimental.document_explorer.__main__.parse_args")
    @patch("shesha.experimental.document_explorer.__main__.uvicorn")
    @patch("shesha.experimental.document_explorer.__main__.create_api")
    @patch("shesha.experimental.document_explorer.__main__.create_app_state")
    def test_creates_state_with_args(
        self, mock_state: MagicMock, mock_api: MagicMock,
        mock_uvicorn: MagicMock, mock_parse: MagicMock,
    ) -> None:
        mock_parse.return_value = parse_args(
            ["--data-dir", "/tmp/d", "--model", "gpt-5", "--no-browser"]
        )
        mock_state.return_value = MagicMock()
        mock_api.return_value = MagicMock()
        main()
        mock_state.assert_called_once_with(data_dir=Path("/tmp/d"), model="gpt-5")

    @patch("shesha.experimental.document_explorer.__main__.parse_args")
    @patch("shesha.experimental.document_explorer.__main__.uvicorn")
    @patch("shesha.experimental.document_explorer.__main__.create_api")
    @patch("shesha.experimental.document_explorer.__main__.create_app_state")
    def test_runs_uvicorn(
        self, mock_state: MagicMock, mock_api: MagicMock,
        mock_uvicorn: MagicMock, mock_parse: MagicMock,
    ) -> None:
        mock_parse.return_value = parse_args(["--port", "9999", "--no-browser"])
        mock_state.return_value = MagicMock()
        sentinel = MagicMock(name="app")
        mock_api.return_value = sentinel
        main()
        mock_uvicorn.run.assert_called_once_with(sentinel, host="0.0.0.0", port=9999)
```

**Step 2: Run tests — expect FAIL**

**Step 3: Write implementation**

```python
# src/shesha/experimental/document_explorer/__main__.py
"""Document Explorer entry point."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from shesha.experimental.document_explorer.api import create_api
from shesha.experimental.document_explorer.dependencies import create_app_state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shesha Document Explorer")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
```

Note: This depends on `create_api` from Task 7. The tests mock it, so they pass independently.

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/__main__.py \
        tests/unit/experimental/document_explorer/test_main.py
git commit -m "feat(document-explorer): add entry point with TDD"
```

---

## Task 6: API Routes (Upload + CRUD + Topic-Doc References)

**Files:**
- Create: `src/shesha/experimental/document_explorer/api.py`
- Test: `tests/unit/experimental/document_explorer/test_api.py`

This is the largest task. It includes document upload (multipart), listing, getting, downloading, deleting, and topic-document reference routes.

**Step 1: Write failing tests**

```python
# tests/unit/experimental/document_explorer/test_api.py
"""Tests for document explorer API routes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.document_explorer.api import create_api
from shesha.experimental.document_explorer.dependencies import DocumentExplorerState
from shesha.experimental.document_explorer.topics import DocumentTopicManager


@pytest.fixture
def mock_shesha() -> MagicMock:
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha._storage = MagicMock()
    shesha._storage.list_documents.return_value = []
    return shesha


@pytest.fixture
def topic_mgr(tmp_path: Path) -> DocumentTopicManager:
    return DocumentTopicManager(tmp_path / "topics")


@pytest.fixture
def uploads_dir(tmp_path: Path) -> Path:
    d = tmp_path / "uploads"
    d.mkdir()
    return d


@pytest.fixture
def state(
    mock_shesha: MagicMock, topic_mgr: DocumentTopicManager, uploads_dir: Path,
) -> DocumentExplorerState:
    return DocumentExplorerState(
        shesha=mock_shesha, topic_mgr=topic_mgr,
        session=MagicMock(), model="test-model", uploads_dir=uploads_dir,
    )


@pytest.fixture
def client(state: DocumentExplorerState) -> TestClient:
    app = create_api(state)
    return TestClient(app)


class TestListDocuments:
    def test_empty(self, client: TestClient, mock_shesha: MagicMock) -> None:
        mock_shesha.list_projects.return_value = []
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_documents(
        self, client: TestClient, mock_shesha: MagicMock, uploads_dir: Path,
    ) -> None:
        mock_shesha.list_projects.return_value = ["report-a3f2"]
        doc_dir = uploads_dir / "report-a3f2"
        doc_dir.mkdir()
        (doc_dir / "meta.json").write_text(json.dumps({
            "filename": "report.pdf", "content_type": "application/pdf",
            "size": 1024, "upload_date": "2026-03-05T12:00:00Z", "page_count": 5,
        }))
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "report-a3f2"
        assert data[0]["filename"] == "report.pdf"


class TestUploadDocument:
    def test_upload_single_file(
        self, client: TestClient, mock_shesha: MagicMock, uploads_dir: Path,
    ) -> None:
        mock_shesha.create_project.return_value = MagicMock()

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("hello.txt", b"Hello content", "text/plain"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["filename"] == "hello.txt"
        assert data[0]["status"] == "created"

    def test_upload_multiple_files(
        self, client: TestClient, mock_shesha: MagicMock, uploads_dir: Path,
    ) -> None:
        mock_shesha.create_project.return_value = MagicMock()

        resp = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("a.txt", b"AAA", "text/plain")),
                ("files", ("b.txt", b"BBB", "text/plain")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_upload_to_topic(
        self, client: TestClient, mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager, uploads_dir: Path,
    ) -> None:
        mock_shesha.create_project.return_value = MagicMock()
        topic_mgr.create("Research")

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Notes", "text/plain"))],
            data={"topic": "Research"},
        )
        assert resp.status_code == 200
        pid = resp.json()[0]["project_id"]
        assert pid in topic_mgr.list_docs("Research")


class TestDeleteDocument:
    def test_delete_removes_from_topics(
        self, client: TestClient, mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager, uploads_dir: Path,
    ) -> None:
        topic_mgr.create("A")
        topic_mgr.add_doc("A", "doc-123")
        # Set up upload dir so delete can clean it up
        (uploads_dir / "doc-123").mkdir()
        (uploads_dir / "doc-123" / "meta.json").write_text("{}")
        (uploads_dir / "doc-123" / "original.txt").write_text("x")

        resp = client.delete("/api/documents/doc-123")
        assert resp.status_code == 200
        assert "doc-123" not in topic_mgr.list_docs("A")
        mock_shesha.delete_project.assert_called_once_with("doc-123")


class TestTopicDocumentRoutes:
    def test_list_topic_documents(
        self, client: TestClient, mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager, uploads_dir: Path,
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_doc("Research", "doc-1")
        doc_dir = uploads_dir / "doc-1"
        doc_dir.mkdir()
        (doc_dir / "meta.json").write_text(json.dumps({
            "filename": "paper.pdf", "content_type": "application/pdf",
            "size": 2048, "upload_date": "2026-03-05", "page_count": 10,
        }))
        resp = client.get("/api/topics/Research/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "doc-1"

    def test_add_doc_to_topic(
        self, client: TestClient, topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        resp = client.post("/api/topics/Research/documents/doc-1")
        assert resp.status_code == 200
        assert "doc-1" in topic_mgr.list_docs("Research")

    def test_remove_doc_from_topic(
        self, client: TestClient, topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_doc("Research", "doc-1")
        resp = client.delete("/api/topics/Research/documents/doc-1")
        assert resp.status_code == 200
        assert "doc-1" not in topic_mgr.list_docs("Research")
```

**Step 2: Run tests — expect FAIL**

**Step 3: Write implementation**

```python
# src/shesha/experimental/document_explorer/api.py
"""Document explorer API.

Provides document upload, CRUD, and topic-document reference routes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, UploadFile

from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from shesha.experimental.document_explorer.extractors import extract_text, get_page_count
from shesha.experimental.document_explorer.schemas import (
    DocumentInfo,
    DocumentUploadResponse,
    TopicCreate,
    TopicRename,
)
from shesha.experimental.document_explorer.topics import _slugify
from shesha.experimental.document_explorer.websockets import websocket_handler
from shesha.experimental.shared.app_factory import create_app
from shesha.experimental.shared.routes import create_shared_router
from shesha.experimental.shared.schemas import TopicInfo
from shesha.models import ParsedDocument


def _make_project_id(filename: str) -> str:
    """Generate project_id from filename: slugified-name-xxxx."""
    stem = Path(filename).stem
    slug = _slugify(stem) or "document"
    short_hash = hashlib.sha256(
        f"{filename}-{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:4]
    return f"{slug}-{short_hash}"


def _read_upload_meta(uploads_dir: Path, project_id: str) -> dict | None:
    meta_path = uploads_dir / project_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _build_doc_info(uploads_dir: Path, project_id: str) -> DocumentInfo | None:
    meta = _read_upload_meta(uploads_dir, project_id)
    if meta is None:
        return None
    return DocumentInfo(
        project_id=project_id,
        filename=meta.get("filename", ""),
        content_type=meta.get("content_type", ""),
        size=meta.get("size", 0),
        upload_date=meta.get("upload_date", ""),
        page_count=meta.get("page_count"),
    )


def _build_doc_topic_info(state: DocumentExplorerState) -> list[TopicInfo]:
    names = state.topic_mgr.list_topics()
    return [
        TopicInfo(
            name=n,
            document_count=len(state.topic_mgr.list_docs(n)),
            size="",
            project_id=f"topic:{n}",
        )
        for n in names
    ]


def _resolve_doc_project_ids(
    state: DocumentExplorerState, topic_name: str,
) -> list[str]:
    try:
        docs = state.topic_mgr.list_docs(topic_name)
        if docs:
            return docs
    except ValueError:
        pass
    return state.shesha.list_projects()


def _list_doc_trace_files(
    state: DocumentExplorerState, project_id: str,
) -> list[Path]:
    return state.shesha._storage.list_traces(project_id)


def _create_document_router(state: DocumentExplorerState) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/documents")
    def list_documents() -> list[DocumentInfo]:
        project_ids = state.shesha.list_projects()
        result: list[DocumentInfo] = []
        for pid in project_ids:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.get("/documents/uncategorized")
    def list_uncategorized() -> list[DocumentInfo]:
        all_ids = state.shesha.list_projects()
        uncategorized = state.topic_mgr.list_uncategorized_docs(all_ids)
        result: list[DocumentInfo] = []
        for pid in uncategorized:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.post("/documents/upload")
    async def upload_documents(
        files: list[UploadFile],
        topic: str | None = None,
    ) -> list[DocumentUploadResponse]:
        results: list[DocumentUploadResponse] = []
        for file in files:
            if not file.filename:
                continue

            project_id = _make_project_id(file.filename)

            # Save original file
            upload_dir = state.uploads_dir / project_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            content = await file.read()

            ext = Path(file.filename).suffix
            original_path = upload_dir / f"original{ext}"
            original_path.write_bytes(content)

            # Extract text
            try:
                text = extract_text(original_path)
            except ValueError as exc:
                shutil.rmtree(upload_dir)
                raise HTTPException(422, str(exc)) from exc

            # Compute page/sheet/slide count where applicable
            page_count = get_page_count(original_path)

            # Save upload metadata
            meta = {
                "filename": file.filename,
                "content_type": file.content_type or "application/octet-stream",
                "size": len(content),
                "upload_date": datetime.now(timezone.utc).isoformat(),
                "page_count": page_count,
            }
            (upload_dir / "meta.json").write_text(json.dumps(meta, indent=2))

            # Create Shesha project and store extracted text
            state.shesha.create_project(project_id)
            doc = ParsedDocument(
                name=file.filename,
                content=text,
                format=ext.lstrip(".") or "txt",
                metadata={"filename": file.filename, "size": len(content)},
                char_count=len(text),
            )
            state.shesha._storage.save_document(project_id, doc)

            # Add to topic if specified
            if topic:
                state.topic_mgr.create(topic)
                state.topic_mgr.add_doc(topic, project_id)

            results.append(DocumentUploadResponse(
                project_id=project_id,
                filename=file.filename,
                status="created",
            ))
        return results

    @router.get("/documents/{doc_id}")
    def get_document(doc_id: str) -> DocumentInfo:
        info = _build_doc_info(state.uploads_dir, doc_id)
        if info is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")
        return info

    @router.delete("/documents/{doc_id}")
    def delete_document(doc_id: str) -> dict[str, str]:
        state.topic_mgr.remove_doc_from_all(doc_id)
        # Remove upload files
        upload_dir = state.uploads_dir / doc_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        # Remove Shesha project
        state.shesha.delete_project(doc_id)
        return {"status": "deleted", "project_id": doc_id}

    @router.get("/documents/{doc_id}/download")
    def download_document(doc_id: str) -> dict[str, str]:
        upload_dir = state.uploads_dir / doc_id
        if not upload_dir.exists():
            raise HTTPException(404, f"Document '{doc_id}' not found")
        # Find the original file
        originals = [f for f in upload_dir.iterdir() if f.name.startswith("original")]
        if not originals:
            raise HTTPException(404, f"Original file not found for '{doc_id}'")
        from fastapi.responses import FileResponse

        meta = _read_upload_meta(state.uploads_dir, doc_id)
        filename = meta.get("filename", "download") if meta else "download"
        return FileResponse(originals[0], filename=filename)  # type: ignore[return-value]

    # --- Topic CRUD ---

    @router.get("/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        return _build_doc_topic_info(state)

    @router.post("/topics", status_code=201)
    def create_topic(body: TopicCreate) -> dict[str, str]:
        state.topic_mgr.create(body.name)
        return {"name": body.name, "project_id": ""}

    @router.patch("/topics/{name}")
    def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
        try:
            state.topic_mgr.rename(name, body.new_name)
        except ValueError as e:
            status = 409 if "already exists" in str(e) else 404
            raise HTTPException(status, str(e)) from e
        return {"name": body.new_name}

    @router.delete("/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            state.topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"status": "deleted", "name": name}

    # --- Topic-document references ---

    @router.get("/topics/{name}/documents")
    def list_topic_docs(name: str) -> list[DocumentInfo]:
        try:
            doc_ids = state.topic_mgr.list_docs(name)
        except ValueError:
            raise HTTPException(404, f"Topic '{name}' not found")
        result: list[DocumentInfo] = []
        for pid in doc_ids:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.post("/topics/{name}/documents/{doc_id}")
    def add_doc_to_topic(name: str, doc_id: str) -> dict[str, str]:
        state.topic_mgr.create(name)
        state.topic_mgr.add_doc(name, doc_id)
        return {"status": "added", "topic": name, "project_id": doc_id}

    @router.delete("/topics/{name}/documents/{doc_id}")
    def remove_doc_from_topic(name: str, doc_id: str) -> dict[str, str]:
        try:
            state.topic_mgr.remove_doc(name, doc_id)
        except ValueError:
            raise HTTPException(404, f"Doc '{doc_id}' not found in topic '{name}'")
        return {"status": "removed", "topic": name, "project_id": doc_id}

    return router


def create_api(state: DocumentExplorerState) -> FastAPI:
    doc_router = _create_document_router(state)
    shared_router = create_shared_router(
        state,
        get_session=lambda s, name: get_topic_session(state, name),
        build_topic_info=lambda s: _build_doc_topic_info(state),
        resolve_project_ids=lambda s, name: _resolve_doc_project_ids(state, name),
        list_trace_files=lambda s, pid: _list_doc_trace_files(state, pid),
        include_topic_crud=False,
        include_per_topic_history=True,
        include_context_budget=True,
    )
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    return create_app(
        state,
        title="Shesha Document Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[doc_router, shared_router],
    )
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/api.py \
        tests/unit/experimental/document_explorer/test_api.py
git commit -m "feat(document-explorer): add API routes with TDD"
```

---

## Task 7: WebSocket Handler

**Files:**
- Create: `src/shesha/experimental/document_explorer/websockets.py`
- Test: `tests/unit/experimental/document_explorer/test_ws.py`

**Step 1: Write failing tests**

```python
# tests/unit/experimental/document_explorer/test_ws.py
"""Tests for document explorer WebSocket handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from shesha.experimental.document_explorer.websockets import websocket_handler
from shesha.models import ParsedDocument
from shesha.rlm.trace import TokenUsage, Trace


def _make_doc(name: str) -> ParsedDocument:
    return ParsedDocument(
        name=name, content=f"Content of {name}",
        format="text", metadata={}, char_count=len(f"Content of {name}"),
    )


def _make_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.session.format_history_prefix.return_value = ""
    return state


def _make_app(state: MagicMock) -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await websocket_handler(ws, state)

    return app


class TestQueryDocuments:
    def test_loads_docs_and_returns_answer(self, tmp_path: Path) -> None:
        mock_state = _make_state()
        mock_result = MagicMock()
        mock_result.answer = "Document answer"
        mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        mock_result.execution_time = 1.5
        mock_result.trace = Trace(steps=[])

        mock_project = MagicMock()
        mock_project._rlm_engine.query.return_value = mock_result

        mock_state.shesha._storage.list_documents.return_value = ["content.json"]
        mock_state.shesha._storage.get_document.side_effect = lambda pid, name: _make_doc(name)
        mock_state.shesha._storage.list_traces.return_value = []
        mock_state.shesha.get_project.return_value = mock_project

        app = _make_app(mock_state)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "query",
                "question": "What does the report say?",
                "document_ids": ["report-a3f2"],
            })
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        complete = [m for m in messages if m["type"] == "complete"]
        assert len(complete) == 1
        assert complete[0]["answer"] == "Document answer"
        assert complete[0]["document_ids"] == ["report-a3f2"]


class TestEmptyDocumentIds:
    def test_error_on_empty(self) -> None:
        mock_state = _make_state()
        app = _make_app(mock_state)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "query", "question": "What?", "document_ids": [],
            })
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "select" in msg["message"].lower() or "document" in msg["message"].lower()
```

**Step 2: Run tests — expect FAIL**

**Step 3: Write implementation**

```python
# src/shesha/experimental/document_explorer/websockets.py
"""Document explorer WebSocket handler.

Same pattern as the code explorer: document_ids are project_ids,
queries span multiple projects, per-topic sessions for history.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from fastapi import WebSocket

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from shesha.experimental.shared.websockets import websocket_handler as shared_ws_handler
from shesha.models import ParsedDocument
from shesha.rlm.trace import StepType, TokenUsage

logger = logging.getLogger(__name__)


async def websocket_handler(ws: WebSocket, state: DocumentExplorerState) -> None:
    await shared_ws_handler(ws, state, query_handler=_handle_query)


async def _handle_query(
    ws: WebSocket,
    data: dict[str, Any],
    state: Any,
    cancel_event: threading.Event,
) -> None:
    question = str(data.get("question", ""))
    document_ids = data.get("document_ids")

    if not document_ids or not isinstance(document_ids, list) or len(document_ids) == 0:
        await ws.send_json({
            "type": "error",
            "message": "Please select one or more documents before querying",
        })
        return

    # Load documents from all requested projects
    loaded_docs: list[ParsedDocument] = []
    storage = state.shesha._storage
    for project_id in document_ids:
        project_id_str = str(project_id)
        try:
            doc_names = storage.list_documents(project_id_str)
            for doc_name in doc_names:
                doc = storage.get_document(project_id_str, doc_name)
                loaded_docs.append(doc)
        except Exception:
            logger.warning("Could not load documents from project %s", project_id_str)

    if not loaded_docs:
        await ws.send_json(
            {"type": "error", "message": "No documents found in selected items"}
        )
        return

    # Build context with document metadata (filename, type)
    context_parts: list[str] = []
    for project_id in document_ids:
        pid_str = str(project_id)
        meta_path = state.uploads_dir / pid_str / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                filename = meta.get("filename", pid_str)
                content_type = meta.get("content_type", "unknown")
                context_parts.append(
                    f"--- Document: {filename} (type: {content_type}) ---"
                )
            except Exception:
                pass

    # Resolve session
    topic_name = str(data.get("topic", ""))
    session = get_topic_session(state, topic_name) if topic_name else state.session

    # Build question with history and document context
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question
    if context_parts:
        full_question += "\n\n" + "\n".join(context_parts)

    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(
        step_type: StepType, iteration: int, content: str, token_usage: TokenUsage,
    ) -> None:
        step_msg: dict[str, object] = {
            "type": "step", "step_type": step_type.value,
            "iteration": iteration, "content": content,
        }
        if token_usage.prompt_tokens > 0:
            step_msg["prompt_tokens"] = token_usage.prompt_tokens
            step_msg["completion_tokens"] = token_usage.completion_tokens
        loop.call_soon_threadsafe(message_queue.put_nowait, step_msg)

    await ws.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    first_project_id = str(document_ids[0])
    try:
        project = state.shesha.get_project(first_project_id)
    except ProjectNotFoundError:
        await ws.send_json(
            {"type": "error", "message": f"Document {first_project_id} not found"}
        )
        await message_queue.put(None)
        await drain_task
        return
    rlm_engine = project._rlm_engine
    if rlm_engine is None:
        await ws.send_json({"type": "error", "message": "Query engine not configured"})
        await message_queue.put(None)
        await drain_task
        return

    try:
        result = await loop.run_in_executor(
            None,
            lambda: rlm_engine.query(
                documents=[d.content for d in loaded_docs],
                question=full_question,
                doc_names=[d.name for d in loaded_docs],
                on_progress=on_progress,
                storage=storage,
                project_id=first_project_id,
                cancel_event=cancel_event,
            ),
        )
    except Exception as exc:
        await message_queue.put(None)
        await drain_task
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    await message_queue.put(None)
    await drain_task

    trace_id = None
    traces = storage.list_traces(first_project_id)
    if traces:
        trace_id = traces[-1].stem

    consulted_ids = [str(pid) for pid in document_ids]
    document_bytes = sum(len(d.content.encode("utf-8")) for d in loaded_docs)

    session.add_exchange(
        question=question, answer=result.answer, trace_id=trace_id,
        tokens={
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        execution_time=result.execution_time,
        model=state.model,
        document_ids=consulted_ids,
    )

    await ws.send_json({
        "type": "complete", "answer": result.answer, "trace_id": trace_id,
        "tokens": {
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        "duration_ms": int(result.execution_time * 1000),
        "document_ids": consulted_ids,
        "document_bytes": document_bytes,
    })
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/document_explorer/websockets.py \
        tests/unit/experimental/document_explorer/test_ws.py
git commit -m "feat(document-explorer): add WebSocket handler with TDD"
```

---

## Task 8: pyproject.toml Updates

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add entry point and document-explorer extra**

Add to `[project.scripts]`:
```toml
shesha-document-explorer = "shesha.experimental.document_explorer.__main__:main"
```

Add a new `[project.optional-dependencies]` section (note: `python-docx` and
`pdfplumber` are already core dependencies, so only new packages go here):
```toml
document-explorer = [
    "shesha[web]",
    "python-pptx>=1.0",
    "openpyxl>=3.1",
    "striprtf>=0.0.26",
    "python-multipart>=0.0.9",
]
```

Also add `"python-pptx"`, `"openpyxl"`, `"striprtf"`, and `"python-multipart"`
to the `dev` extra so that tests can run.

**Step 2: Verify install**

Run: `pip install -e ".[document-explorer,dev]"`
Expected: installs without errors, `shesha-document-explorer --help` works.

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(document-explorer): add entry point and dependencies"
```

---

## Task 9: Frontend

**Files:**
- Create: `src/shesha/experimental/document_explorer/frontend/` (all files)

This task creates the complete frontend. Follow the code explorer frontend structure exactly with these changes:
- `repos` → `documents` terminology
- `AddRepoModal` → `UploadArea` (inline drag-and-drop zone + file picker)
- `RepoDetail` → `DocumentDetail` (metadata + download + topic membership)
- API client uses `/api/documents` routes

### Subtask 9a: Frontend scaffold (package.json, configs, index.html, main.tsx, index.css)

Copy from code explorer, update:
- `package.json`: name → `"document-explorer-frontend"`, proxy target → `localhost:8003`
- `vite.config.ts`: proxy target → `http://localhost:8003`
- `index.html`: title → `Shesha Document Explorer`

### Subtask 9b: Types and API client

```typescript
// src/types.ts
export type { DocumentItem, Exchange, TopicInfo } from '@shesha/shared-ui'

export interface DocumentInfo {
  project_id: string
  filename: string
  content_type: string
  size: number
  upload_date: string
  page_count: number | null
}
```

```typescript
// src/api/client.ts
import { request, sharedApi } from '@shesha/shared-ui'
import type { DocumentInfo } from '../types'

export const api = {
  ...sharedApi,

  documents: {
    list: () => request<DocumentInfo[]>('/documents'),
    listUncategorized: () => request<DocumentInfo[]>('/documents/uncategorized'),
    listForTopic: (topic: string) =>
      request<DocumentInfo[]>(`/topics/${encodeURIComponent(topic)}/documents`),
    get: (id: string) => request<DocumentInfo>(`/documents/${encodeURIComponent(id)}`),
    delete: (id: string) =>
      request<{ status: string }>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    upload: (files: File[], topic?: string) => {
      const formData = new FormData()
      for (const file of files) formData.append('files', file)
      if (topic) formData.append('topic', topic)
      return request<{ project_id: string; filename: string; status: string }[]>(
        '/documents/upload',
        { method: 'POST', body: formData },
      )
    },
  },

  topicDocs: {
    add: (topic: string, docId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/documents/${encodeURIComponent(docId)}`,
        { method: 'POST' },
      ),
    remove: (topic: string, docId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/documents/${encodeURIComponent(docId)}`,
        { method: 'DELETE' },
      ),
  },
}
```

### Subtask 9c: UploadArea component

Inline drag-and-drop zone + file picker (not a modal). Supports multiple files.
Shows upload progress per file. On drop/pick, calls `api.documents.upload()` for
each file. Placed above the document list in the sidebar.

### Subtask 9d: DocumentItem component

Sidebar row component: file-type icon (PDF, Word, Excel, PPT, text), filename,
size sublabel (e.g. "42 KB"). Used by `TopicSidebar` to render each document.

### Subtask 9e: DocumentDetail component

Shows metadata (filename, type, size, upload date, page count), download button, topic membership list, delete button.

### Subtask 9f: App.tsx

Follow code explorer `App.tsx` structure with document terminology. Key changes:
- `selectedRepos` → `selectedDocs`
- `allRepos` → `allDocs`
- `repoToDocument()` helper maps `DocumentInfo` → `DocumentItem`
- `UploadArea` inline component instead of modal pattern
- `DocumentItem` component for sidebar rows with file-type icons
- `appName="Document Explorer"`

### Subtask 9g: Build and verify

Run: `cd src/shesha/experimental/document_explorer/frontend && npm install && npm run build`
Expected: `dist/` directory created

**Commit after each working subtask.**

---

## Task 10: Docker & Launch Script

**Files:**
- Create: `document-explorer/Dockerfile`
- Create: `document-explorer/docker-compose.yml`
- Create: `document-explorer/document-explorer.sh`

### Dockerfile

Same as code explorer but:
- No `git` install (not needed)
- Paths point to `document_explorer`
- Port 8003
- Entrypoint: `shesha-document-explorer`

### docker-compose.yml

```yaml
services:
  shesha-document-explorer:
    build:
      context: ..
      dockerfile: document-explorer/Dockerfile
    ports:
      - "8003:8003"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - shesha-doc-data:/data
    environment:
      - SHESHA_API_KEY=${SHESHA_API_KEY:?Set SHESHA_API_KEY}
      - SHESHA_MODEL=${SHESHA_MODEL:?Set SHESHA_MODEL}

volumes:
  shesha-doc-data:
```

### Launch script

Copy `code-explorer.sh`, update paths and remove `git` prerequisite check.

**Commit:**

```bash
git add document-explorer/
git commit -m "feat(document-explorer): add Docker and launch script"
```

---

## Task 11: Integration Smoke Test

**Step 1:** Run all document explorer tests:

```bash
python -m pytest tests/unit/experimental/document_explorer/ -v
```

Expected: all pass.

**Step 2:** Run linting and type checking:

```bash
ruff check src/shesha/experimental/document_explorer tests/unit/experimental/document_explorer
ruff format src/shesha/experimental/document_explorer tests/unit/experimental/document_explorer
mypy src/shesha/experimental/document_explorer
```

**Step 3:** Run full test suite:

```bash
make all
```

Expected: everything passes.

**Step 4:** Final commit if any fixups needed.
