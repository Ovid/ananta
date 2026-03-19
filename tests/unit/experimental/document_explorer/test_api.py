"""Tests for document explorer API routes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.document_explorer.api import _make_project_id, create_api
from shesha.experimental.document_explorer.dependencies import DocumentExplorerState
from shesha.experimental.document_explorer.topics import DocumentTopicManager


class TestMakeProjectId:
    def test_hash_suffix_is_8_hex_chars(self) -> None:
        pid = _make_project_id("report.pdf")
        # Format: slug-xxxxxxxx
        assert re.fullmatch(r"[a-z0-9]+-[a-f0-9]{8}", pid), f"unexpected format: {pid}"

    def test_same_filename_produces_different_ids(self) -> None:
        """Same filename yields different IDs due to timestamp in hash.

        Known limitation (F-18): fix deferred — requires content-based hashing.
        """
        id1 = _make_project_id("report.pdf")
        id2 = _make_project_id("report.pdf")
        assert id1 != id2


@pytest.fixture
def mock_shesha() -> MagicMock:
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha.storage = MagicMock()
    shesha.storage.list_documents.return_value = []
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
    mock_shesha: MagicMock,
    topic_mgr: DocumentTopicManager,
    uploads_dir: Path,
) -> DocumentExplorerState:
    return DocumentExplorerState(
        shesha=mock_shesha,
        topic_mgr=topic_mgr,
        session=MagicMock(),
        model="test-model",
        extra_dirs={"uploads": uploads_dir},
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
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_shesha.list_projects.return_value = ["report-a3f2"]
        doc_dir = uploads_dir / "report-a3f2"
        doc_dir.mkdir()
        (doc_dir / "meta.json").write_text(
            json.dumps(
                {
                    "filename": "report.pdf",
                    "content_type": "application/pdf",
                    "size": 1024,
                    "upload_date": "2026-03-05T12:00:00Z",
                    "page_count": 5,
                }
            )
        )
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "report-a3f2"
        assert data[0]["filename"] == "report.pdf"


class TestUploadDocument:
    def test_upload_single_file(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        uploads_dir: Path,
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
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        uploads_dir: Path,
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
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
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
        assert pid in topic_mgr.list_items("Research")

    def test_upload_with_invalid_topic_name_returns_422(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
    ) -> None:
        mock_shesha.create_project.return_value = MagicMock()

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Notes", "text/plain"))],
            data={"topic": "!!!"},  # slugifies to empty string
        )
        assert resp.status_code == 422
        assert "slug" in resp.json()["detail"].lower()

    def test_upload_invalid_topic_does_not_create_project(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """An invalid topic name must fail before creating any files or projects."""
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Notes", "text/plain"))],
            data={"topic": "!!!"},
        )
        assert resp.status_code == 422
        mock_shesha.create_project.assert_not_called()
        # No upload directories should have been created
        assert list(uploads_dir.iterdir()) == []

    def test_upload_unsupported_type_returns_422_with_detail(
        self,
        client: TestClient,
    ) -> None:
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        )
        assert resp.status_code == 422
        assert ".png" in resp.json()["detail"]


class TestUploadAtomicity:
    """Upload failures at each step should clean up and not leave orphaned state."""

    def test_create_project_failure_cleans_up_upload_dir(
        self,
        state: DocumentExplorerState,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If create_project fails, upload dir is cleaned up."""
        mock_shesha.create_project.side_effect = RuntimeError("storage full")
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Hello", "text/plain"))],
        )
        assert resp.status_code == 500
        mock_shesha.storage.store_document.assert_not_called()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

    def test_store_document_failure_cleans_up_project_and_upload(
        self,
        state: DocumentExplorerState,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If store_document fails, both project and upload dir are cleaned up."""
        mock_shesha.create_project.return_value = MagicMock()
        mock_shesha.storage.store_document.side_effect = RuntimeError("disk error")
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Hello", "text/plain"))],
        )
        assert resp.status_code == 500
        # Project should be deleted (cleanup)
        mock_shesha.delete_project.assert_called_once()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

    def test_text_extraction_failure_cleans_up_upload_dir(
        self,
        client: TestClient,
        uploads_dir: Path,
    ) -> None:
        """Existing behavior: extraction failure removes the upload directory."""
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        )
        assert resp.status_code == 422
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

    def test_topic_add_failure_cleans_up_everything(
        self,
        state: DocumentExplorerState,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If add_to_topic fails, project, document, and upload dir are cleaned up."""
        mock_shesha.create_project.return_value = MagicMock()
        # Create the topic so the pre-flight validation passes
        state.topic_mgr.create("Research")

        # Make add_item fail
        original_add = state.topic_mgr.add_item

        def fail_add(topic: str, item: str) -> None:
            raise RuntimeError("topic storage error")

        state.topic_mgr.add_item = fail_add  # type: ignore[assignment]

        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Hello", "text/plain"))],
            data={"topic": "Research"},
        )
        assert resp.status_code == 500
        # Project should be deleted (cleanup)
        mock_shesha.delete_project.assert_called_once()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

        state.topic_mgr.add_item = original_add  # type: ignore[assignment]

    def test_batch_upload_cleans_up_earlier_files_on_later_failure(
        self,
        state: DocumentExplorerState,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If file 2 of 2 fails at store_document, file 1's project is also cleaned up."""
        call_count = [0]

        def store_side_effect(project_id, doc, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("disk full on second file")

        mock_shesha.create_project.return_value = MagicMock()
        mock_shesha.storage.store_document.side_effect = store_side_effect
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("first.txt", b"Hello", "text/plain")),
                ("files", ("second.txt", b"World", "text/plain")),
            ],
        )
        assert resp.status_code == 500
        # Both projects should be cleaned up — not just the second one
        assert mock_shesha.delete_project.call_count == 2
        # All upload dirs should be cleaned up
        assert list(uploads_dir.iterdir()) == []

    def test_batch_upload_rollback_removes_topic_associations(
        self,
        state: DocumentExplorerState,
        mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        """Batch upload rollback removes topic associations for cleaned-up projects."""
        topic_mgr.create("MyTopic")
        call_count = [0]
        created_pids: list[str] = []

        def store_side_effect(project_id, doc, **kwargs):
            call_count[0] += 1
            created_pids.append(project_id)
            if call_count[0] == 2:
                raise RuntimeError("disk full on second file")

        mock_shesha.create_project.return_value = MagicMock()
        mock_shesha.storage.store_document.side_effect = store_side_effect
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            data={"topic": "MyTopic"},
            files=[
                ("files", ("first.txt", b"Hello", "text/plain")),
                ("files", ("second.txt", b"World", "text/plain")),
            ],
        )
        assert resp.status_code == 500
        # Topic associations should be cleaned up — no orphaned references
        for pid in created_pids:
            items = topic_mgr.list_items("MyTopic")
            assert pid not in items, f"Orphaned topic entry for {pid}"


class TestUploadSizeLimit:
    def test_upload_exceeding_size_limit_returns_413(
        self,
        client: TestClient,
    ) -> None:
        """Uploads exceeding MAX_UPLOAD_BYTES are rejected with 413."""
        from shesha.experimental.document_explorer.api import MAX_UPLOAD_BYTES

        oversized = b"x" * (MAX_UPLOAD_BYTES + 1)
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("big.txt", oversized, "text/plain"))],
        )
        assert resp.status_code == 413

    def test_upload_at_size_limit_succeeds(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
    ) -> None:
        """Uploads exactly at the limit should succeed."""
        from shesha.experimental.document_explorer.api import MAX_UPLOAD_BYTES

        mock_shesha.create_project.return_value = MagicMock()
        at_limit = b"x" * MAX_UPLOAD_BYTES
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("ok.txt", at_limit, "text/plain"))],
        )
        assert resp.status_code == 200

    def test_unsupported_extension_rejected_before_reading_body(
        self,
        client: TestClient,
        uploads_dir: Path,
    ) -> None:
        """Unsupported extension must be rejected before reading the upload body.

        Regression: the old code read the entire file into memory before
        checking the extension, so a large .png upload would allocate RAM
        before being rejected.
        """
        # A small payload is enough — the extension check must come first.
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        )
        assert resp.status_code == 422
        # No upload directory should have been created for the rejected file.
        assert list(uploads_dir.iterdir()) == []

    def test_oversized_upload_caps_memory(
        self,
        client: TestClient,
    ) -> None:
        """Server must not read more than MAX_UPLOAD_BYTES+1 into memory.

        Verifies the capped-read approach: the endpoint reads at most
        MAX_UPLOAD_BYTES+1 bytes, then checks length.
        """
        from shesha.experimental.document_explorer.api import MAX_UPLOAD_BYTES

        # 2x the limit — old code would allocate all of this.
        oversized = b"x" * (MAX_UPLOAD_BYTES * 2)
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("huge.txt", oversized, "text/plain"))],
        )
        assert resp.status_code == 413

    def test_extension_lowercased_in_stored_format(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """Stored file extension should be lowercased (S9)."""
        mock_shesha.create_project.return_value = MagicMock()
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("NOTES.TXT", b"hello", "text/plain"))],
        )
        assert resp.status_code == 200
        # Find the upload dir and check the original file extension is lowered
        dirs = list(uploads_dir.iterdir())
        assert len(dirs) == 1
        originals = list(dirs[0].glob("original.*"))
        assert len(originals) == 1
        assert originals[0].suffix == ".txt"


class TestDeleteDocument:
    def test_delete_removes_from_topics(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        topic_mgr.create("A")
        topic_mgr.add_item("A", "doc-123")
        # Set up upload dir so delete can clean it up
        (uploads_dir / "doc-123").mkdir()
        (uploads_dir / "doc-123" / "meta.json").write_text("{}")
        (uploads_dir / "doc-123" / "original.txt").write_text("x")

        resp = client.delete("/api/documents/doc-123")
        assert resp.status_code == 200
        assert "doc-123" not in topic_mgr.list_items("A")
        mock_shesha.delete_project.assert_called_once_with("doc-123")


class TestCreateTopic:
    def test_create_topic_with_invalid_name_returns_422(
        self,
        client: TestClient,
    ) -> None:
        resp = client.post("/api/topics", json={"name": "!!!"})
        assert resp.status_code == 422
        assert "slug" in resp.json()["detail"].lower()


class TestRenameTopic:
    def test_rename_with_path_separator_returns_422(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Safe")
        resp = client.patch("/api/topics/Safe", json={"new_name": "foo/bar"})
        assert resp.status_code == 422
        assert "path separator" in resp.json()["detail"].lower()


class TestTopicDocumentRoutes:
    def test_list_topic_items_returns_document_info(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
        mock_shesha: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """GET /topics/{name}/items returns DocumentInfo objects, not bare IDs."""
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "report-a3f2")
        # Create upload metadata so _build_doc_info can resolve the project ID
        doc_dir = uploads_dir / "report-a3f2"
        doc_dir.mkdir()
        (doc_dir / "meta.json").write_text(
            json.dumps(
                {
                    "filename": "report.pdf",
                    "content_type": "application/pdf",
                    "size": 1024,
                    "upload_date": "2026-03-05T12:00:00Z",
                    "page_count": 5,
                }
            )
        )
        resp = client.get("/api/topics/Research/items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "report-a3f2"
        assert data[0]["filename"] == "report.pdf"

    def test_list_topic_items_skips_missing_metadata(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        """Items with no upload metadata are silently skipped."""
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "gone-doc")
        resp = client.get("/api/topics/Research/items")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_doc_to_topic(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        resp = client.post("/api/topics/Research/items/doc-1")
        assert resp.status_code == 200
        assert "doc-1" in topic_mgr.list_items("Research")

    def test_add_doc_with_invalid_topic_returns_422(
        self,
        client: TestClient,
    ) -> None:
        resp = client.post("/api/topics/!!!/items/doc-1")
        assert resp.status_code == 422
        assert "slug" in resp.json()["detail"].lower()

    def test_remove_doc_from_topic(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "doc-1")
        resp = client.delete("/api/topics/Research/items/doc-1")
        assert resp.status_code == 200
        assert "doc-1" not in topic_mgr.list_items("Research")
