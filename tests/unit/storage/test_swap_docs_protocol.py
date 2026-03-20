"""Tests for swap_docs on StorageBackend protocol — non-atomic fallback."""

from pathlib import Path

from shesha.models import ParsedDocument
from shesha.storage.base import default_swap_docs


def _make_doc(name: str, content: str = "content") -> ParsedDocument:
    return ParsedDocument(
        name=name,
        content=content,
        format="txt",
        metadata={},
        char_count=len(content),
        parse_warnings=[],
    )


class MinimalStorage:
    """Minimal StorageBackend implementation using default_swap_docs."""

    def __init__(self) -> None:
        self._projects: dict[str, dict[str, ParsedDocument]] = {}

    def create_project(self, project_id: str) -> None:
        self._projects[project_id] = {}

    def delete_project(self, project_id: str) -> None:
        self._projects.pop(project_id, None)

    def list_projects(self) -> list[str]:
        return list(self._projects.keys())

    def project_exists(self, project_id: str) -> bool:
        return project_id in self._projects

    def store_document(
        self, project_id: str, doc: ParsedDocument, raw_path: Path | None = None
    ) -> None:
        self._projects[project_id][doc.name] = doc

    def get_document(self, project_id: str, doc_name: str) -> ParsedDocument:
        return self._projects[project_id][doc_name]

    def list_documents(self, project_id: str) -> list[str]:
        return list(self._projects[project_id].keys())

    def delete_document(self, project_id: str, doc_name: str) -> None:
        del self._projects[project_id][doc_name]

    def load_all_documents(self, project_id: str) -> list[ParsedDocument]:
        return list(self._projects[project_id].values())

    def get_project_dir(self, project_id: str) -> Path:
        return Path(f"/tmp/{project_id}")

    def get_traces_dir(self, project_id: str) -> Path:
        return Path(f"/tmp/{project_id}/traces")

    def list_traces(self, project_id: str) -> list[Path]:
        return []

    def store_analysis(self, project_id: str, analysis: object) -> None:
        pass

    def load_analysis(self, project_id: str) -> None:
        return None

    def delete_analysis(self, project_id: str) -> None:
        pass

    def swap_docs(self, source_project_id: str, target_project_id: str) -> None:
        default_swap_docs(self, source_project_id, target_project_id)


class TestSwapDocsDefaultFallback:
    """Tests that default_swap_docs does non-atomic doc replacement."""

    def test_swap_docs_replaces_target_docs_with_source_docs(self):
        """default_swap_docs copies source docs to target and removes orphans."""
        storage = MinimalStorage()
        storage.create_project("source")
        storage.create_project("target")

        storage.store_document("source", _make_doc("new.py", "new content"))
        storage.store_document("target", _make_doc("old.py", "old content"))

        storage.swap_docs("source", "target")

        docs = storage.list_documents("target")
        assert "new.py" in docs
        assert "old.py" not in docs

    def test_swap_docs_deletes_source_project(self):
        """default_swap_docs removes the source (staging) project after swap."""
        storage = MinimalStorage()
        storage.create_project("source")
        storage.create_project("target")

        storage.store_document("source", _make_doc("file.py"))
        storage.store_document("target", _make_doc("old.py"))

        storage.swap_docs("source", "target")

        assert not storage.project_exists("source")

    def test_swap_docs_preserves_overlapping_doc_names(self):
        """When source and target share a doc name, source version wins."""
        storage = MinimalStorage()
        storage.create_project("source")
        storage.create_project("target")

        storage.store_document("source", _make_doc("shared.py", "updated"))
        storage.store_document("target", _make_doc("shared.py", "original"))

        storage.swap_docs("source", "target")

        doc = storage.get_document("target", "shared.py")
        assert doc.content == "updated"
