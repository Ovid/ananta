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
    mock_shesha: MagicMock,
    topic_mgr: DocumentTopicManager,
    uploads_dir: Path,
) -> DocumentExplorerState:
    return DocumentExplorerState(
        shesha=mock_shesha,
        topic_mgr=topic_mgr,
        session=MagicMock(),
        model="test-model",
        uploads_dir=uploads_dir,
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
        assert pid in topic_mgr.list_docs("Research")

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


class TestDeleteDocument:
    def test_delete_removes_from_topics(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
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


class TestCreateTopic:
    def test_create_topic_with_invalid_name_returns_422(
        self,
        client: TestClient,
    ) -> None:
        resp = client.post("/api/topics", json={"name": "!!!"})
        assert resp.status_code == 422
        assert "slug" in resp.json()["detail"].lower()


class TestTopicDocumentRoutes:
    def test_list_topic_documents(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_doc("Research", "doc-1")
        doc_dir = uploads_dir / "doc-1"
        doc_dir.mkdir()
        (doc_dir / "meta.json").write_text(
            json.dumps(
                {
                    "filename": "paper.pdf",
                    "content_type": "application/pdf",
                    "size": 2048,
                    "upload_date": "2026-03-05",
                    "page_count": 10,
                }
            )
        )
        resp = client.get("/api/topics/Research/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "doc-1"

    def test_add_doc_to_topic(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        resp = client.post("/api/topics/Research/documents/doc-1")
        assert resp.status_code == 200
        assert "doc-1" in topic_mgr.list_docs("Research")

    def test_remove_doc_from_topic(
        self,
        client: TestClient,
        topic_mgr: DocumentTopicManager,
    ) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_doc("Research", "doc-1")
        resp = client.delete("/api/topics/Research/documents/doc-1")
        assert resp.status_code == 200
        assert "doc-1" not in topic_mgr.list_docs("Research")
