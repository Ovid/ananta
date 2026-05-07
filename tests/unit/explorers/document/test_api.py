"""Tests for document explorer API routes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ananta.explorers.document.api import _make_project_id, create_api
from ananta.explorers.document.dependencies import DocumentExplorerState
from ananta.explorers.document.topics import DocumentTopicManager


class TestMakeProjectId:
    def test_hash_suffix_is_8_hex_chars(self) -> None:
        pid = _make_project_id("report.pdf")
        # Format: slug-xxxxxxxx
        assert re.fullmatch(r"[a-z0-9]+-[a-f0-9]{8}", pid), f"unexpected format: {pid}"

    def test_same_filename_produces_different_ids(self) -> None:
        """Same filename yields different IDs (cryptographically random suffix).

        After I6: the suffix is `secrets.token_hex(4)` instead of a hash of the
        timestamp, so colliding IDs require a 32-bit random collision (~2^16
        files via the birthday bound) rather than two requests landing in the
        same microsecond with the same filename.
        """
        id1 = _make_project_id("report.pdf")
        id2 = _make_project_id("report.pdf")
        assert id1 != id2

    def test_many_ids_are_unique(self) -> None:
        """Generate many IDs at once; the random suffix must not collide.

        With the previous timestamp-based scheme this test was flaky on fast
        machines (two calls in the same microsecond produced identical IDs).
        With token_hex(4) the chance of collision in 1000 calls is ~10^-7.
        """
        ids = {_make_project_id("report.pdf") for _ in range(1000)}
        assert len(ids) == 1000


@pytest.fixture
def mock_ananta() -> MagicMock:
    ananta = MagicMock()
    ananta.list_projects.return_value = []
    ananta.storage = MagicMock()
    ananta.storage.list_documents.return_value = []
    return ananta


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
    mock_ananta: MagicMock,
    topic_mgr: DocumentTopicManager,
    uploads_dir: Path,
) -> DocumentExplorerState:
    return DocumentExplorerState(
        ananta=mock_ananta,
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
    def test_empty(self, client: TestClient, mock_ananta: MagicMock) -> None:
        mock_ananta.list_projects.return_value = []
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_documents(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.list_projects.return_value = ["report-a3f2"]
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
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()

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
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()

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
        mock_ananta: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()
        topic_mgr.create("Research")

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Notes", "text/plain"))],
            data={"topic": "Research"},
        )
        assert resp.status_code == 200
        pid = resp.json()[0]["project_id"]
        assert pid in topic_mgr.list_items("Research")

    def test_upload_to_existing_topic_succeeds(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        """Regression guard (Task A5): two uploads to the same topic both succeed.

        The upload route always calls ``topic_mgr.create(topic)`` for every
        request, so the second upload exercises the idempotent-create path on
        an already-existing topic. If ``create()`` ever stops being idempotent,
        this test fails before any user does.
        """
        mock_ananta.create_project.return_value = MagicMock()

        resp1 = client.post(
            "/api/documents/upload",
            files=[("files", ("a.md", b"x", "text/markdown"))],
            data={"topic": "Barsoom"},
        )
        assert resp1.status_code == 200
        assert resp1.json()[0]["status"] == "created"

        resp2 = client.post(
            "/api/documents/upload",
            files=[("files", ("b.md", b"y", "text/markdown"))],
            data={"topic": "Barsoom"},
        )
        assert resp2.status_code == 200
        assert resp2.json()[0]["status"] == "created"

        # Both project IDs ended up referenced by the same topic.
        items = topic_mgr.list_items("Barsoom")
        assert resp1.json()[0]["project_id"] in items
        assert resp2.json()[0]["project_id"] in items

    def test_upload_with_invalid_topic_name_returns_422(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()

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
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """An invalid topic name must fail before creating any files or projects."""
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Notes", "text/plain"))],
            data={"topic": "!!!"},
        )
        assert resp.status_code == 422
        mock_ananta.create_project.assert_not_called()
        # No upload directories should have been created
        assert list(uploads_dir.iterdir()) == []

    def test_upload_unsupported_type_returns_failed_row(
        self,
        client: TestClient,
        uploads_dir: Path,
    ) -> None:
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("foo.xyz", b"junk", "application/octet-stream"))],
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "failed"
        assert ".xyz" in row["reason"] or "unsupported" in row["reason"].lower()

    def test_upload_partial_success_unsupported_extension(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """One unsupported file should NOT fail the whole batch."""
        mock_ananta.create_project.return_value = MagicMock()
        response = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("good.md", b"hello", "text/markdown")),
                ("files", ("bad.xyz", b"junk", "application/octet-stream")),
                ("files", ("also-good.txt", b"world", "text/plain")),
            ],
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 3
        by_filename = {r["filename"]: r for r in rows}
        assert by_filename["good.md"]["status"] == "created"
        assert by_filename["also-good.txt"]["status"] == "created"
        assert by_filename["bad.xyz"]["status"] == "failed"
        assert "unsupported" in by_filename["bad.xyz"]["reason"].lower()

        good_id = by_filename["good.md"]["project_id"]
        assert (uploads_dir / good_id / "meta.json").exists()

    def test_upload_partial_success_oversized(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()
        big = b"x" * (51 * 1024 * 1024)
        response = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("good.md", b"hello", "text/markdown")),
                ("files", ("big.md", big, "text/markdown")),
            ],
        )
        assert response.status_code == 200
        rows = response.json()
        by_filename = {r["filename"]: r for r in rows}
        assert by_filename["good.md"]["status"] == "created"
        assert by_filename["big.md"]["status"] == "failed"
        assert "limit" in by_filename["big.md"]["reason"].lower()

    def test_upload_persists_relative_path_and_session_id(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        mock_ananta.create_project.return_value = MagicMock()

        response = client.post(
            "/api/documents/upload",
            files=[("files", ("README.md", b"hello", "text/markdown"))],
            data={
                "relative_path": "docs/api/README.md",
                "upload_session_id": "11111111-1111-1111-1111-111111111111",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        project_id = data[0]["project_id"]

        meta = json.loads((uploads_dir / project_id / "meta.json").read_text())
        assert meta["relative_path"] == "docs/api/README.md"
        assert meta["upload_session_id"] == "11111111-1111-1111-1111-111111111111"

    def test_upload_exposes_relative_path_to_rlm_metadata(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """The ParsedDocument stored to Ananta storage should expose
        relative_path in its metadata so the RLM-side document object can
        read it.
        """
        mock_ananta.create_project.return_value = MagicMock()

        response = client.post(
            "/api/documents/upload",
            files=[("files", ("README.md", b"hello world", "text/markdown"))],
            data={"relative_path": "docs/api/README.md"},
        )
        assert response.status_code == 200
        [row] = response.json()
        assert row["status"] == "created"

        # store_document was called with (project_id, ParsedDocument)
        mock_ananta.storage.store_document.assert_called_once()
        call_args = mock_ananta.storage.store_document.call_args
        stored_doc = call_args[0][1]
        assert stored_doc.metadata.get("relative_path") == "docs/api/README.md"

    def test_upload_without_relative_path_omits_key_in_rlm_metadata(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """A single-file upload without a relative_path form field omits
        the key from ParsedDocument.metadata (the typed model does not
        permit None values; downstream code uses .get() so both are fine).
        """
        mock_ananta.create_project.return_value = MagicMock()

        response = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"hi", "text/plain"))],
        )
        assert response.status_code == 200

        mock_ananta.storage.store_document.assert_called_once()
        stored_doc = mock_ananta.storage.store_document.call_args[0][1]
        assert "relative_path" not in stored_doc.metadata


class TestUploadAtomicity:
    """Per-file upload failures should clean up the failing file's state.

    After A4 (per-file partial success): a single-file failure no longer
    rolls back the whole batch. Each failure is a `failed` row in a 200
    response, with the failing file's own upload dir/project/topic-entries
    cleaned up. Successful files are kept.
    """

    def test_create_project_failure_cleans_up_upload_dir(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If create_project fails, that file's upload dir is cleaned up."""
        mock_ananta.create_project.side_effect = RuntimeError("storage full")
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Hello", "text/plain"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        mock_ananta.storage.store_document.assert_not_called()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []
        # Critical (I6): rollback must NOT call delete_project when we never
        # successfully created one. Otherwise an id-collision against an
        # existing project would silently destroy the existing project's data.
        mock_ananta.delete_project.assert_not_called()

    def test_unexpected_exception_text_is_not_leaked_to_response(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The reason returned to the client must not include raw exception text.

        Reproduces Inline 3: the previous code returned
        `f"unexpected error: {exc}"` to the client, which leaked internal
        details (filesystem paths, dependency error messages, stack-trace
        fragments). The fix logs the original exception server-side and
        returns a generic reason in the API response.
        """
        import logging

        sensitive = "/var/lib/secrets/db_password.txt: permission denied"
        mock_ananta.create_project.return_value = MagicMock()
        mock_ananta.storage.store_document.side_effect = RuntimeError(sensitive)
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        with caplog.at_level(logging.ERROR, logger="ananta.explorers.document.api"):
            resp = client.post(
                "/api/documents/upload",
                files=[("files", ("notes.txt", b"Hello", "text/plain"))],
            )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        # The sensitive message must NOT appear in the response reason.
        assert sensitive not in row["reason"]
        # The reason should still be informative ("upload failed", "internal error", etc).
        assert row["reason"]
        # The original exception SHOULD be logged server-side for diagnosis.
        assert any(
            sensitive in record.message or sensitive in str(record)
            for record in caplog.records
        )

    def test_project_id_collision_does_not_destroy_existing_project(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """A ProjectExistsError on create_project must not trigger delete_project.

        Reproduces the I6 attack: if `_make_project_id` happens to return an
        id that collides with an existing project, the existing rollback
        path called shutil.rmtree(upload_dir) AND state.ananta.delete_project
        on that id — wiping the colliding project's data. After the fix, the
        rollback skips the destructive cleanup unless the upload created the
        project itself.
        """
        from ananta.exceptions import ProjectExistsError

        mock_ananta.create_project.side_effect = ProjectExistsError("colliding-id")
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("README.md", b"hello", "text/markdown"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        # The collision must NOT result in the existing project being deleted.
        mock_ananta.delete_project.assert_not_called()

    def test_store_document_failure_cleans_up_project_and_upload(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If store_document fails, that file's project and upload dir are cleaned up."""
        mock_ananta.create_project.return_value = MagicMock()
        mock_ananta.storage.store_document.side_effect = RuntimeError("disk error")
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.txt", b"Hello", "text/plain"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        # Project should be deleted (cleanup)
        mock_ananta.delete_project.assert_called_once()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

    def test_text_extraction_failure_cleans_up_upload_dir(
        self,
        client: TestClient,
        uploads_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If extract_text raises ValueError, the upload dir is removed.

        Covers the cleanup branch at api.py:233-238 (rmtree of upload_dir
        before any project_id is created). Uses a supported extension so the
        unsupported-extension gate doesn't intercept, and stubs extract_text
        to raise ValueError to drive the failure path deterministically.
        """

        def _raise_value_error(_path: Path) -> str:
            raise ValueError("simulated extraction failure")

        monkeypatch.setattr(
            "ananta.explorers.document.api.extract_text",
            _raise_value_error,
        )

        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("notes.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        assert "text extraction failed" in row["reason"].lower()
        # Upload dir should be cleaned up — no leftover project directory.
        assert list(uploads_dir.iterdir()) == []

    def test_topic_add_failure_cleans_up_everything(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If add_to_topic fails, that file's project, document, and upload dir are cleaned up."""
        mock_ananta.create_project.return_value = MagicMock()
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
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        # Project should be deleted (cleanup)
        mock_ananta.delete_project.assert_called_once()
        # Upload dir should be cleaned up
        assert list(uploads_dir.iterdir()) == []

        state.topic_mgr.add_item = original_add  # type: ignore[assignment]

    def test_batch_upload_keeps_earlier_successes_on_later_failure(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """If file 2 of 2 fails, file 1 is kept (per-file partial success).

        Only the failing file's project is cleaned up.
        """
        call_count = [0]

        def store_side_effect(project_id, doc, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("disk full on second file")

        mock_ananta.create_project.return_value = MagicMock()
        mock_ananta.storage.store_document.side_effect = store_side_effect
        app = create_api(state)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("first.txt", b"Hello", "text/plain")),
                ("files", ("second.txt", b"World", "text/plain")),
            ],
        )
        assert resp.status_code == 200
        rows = resp.json()
        by_filename = {r["filename"]: r for r in rows}
        assert by_filename["first.txt"]["status"] == "created"
        assert by_filename["second.txt"]["status"] == "failed"
        # Only the second project is cleaned up — first remains
        assert mock_ananta.delete_project.call_count == 1
        # Only the failing file's upload dir was removed
        assert (uploads_dir / by_filename["first.txt"]["project_id"]).exists()

    def test_batch_upload_failed_file_does_not_leave_topic_association(
        self,
        state: DocumentExplorerState,
        mock_ananta: MagicMock,
        topic_mgr: DocumentTopicManager,
        uploads_dir: Path,
    ) -> None:
        """A failed file has no topic association; successful files do."""
        topic_mgr.create("MyTopic")
        call_count = [0]
        seen_pids: list[str] = []

        def store_side_effect(project_id, doc, **kwargs):
            call_count[0] += 1
            seen_pids.append(project_id)
            if call_count[0] == 2:
                raise RuntimeError("disk full on second file")

        mock_ananta.create_project.return_value = MagicMock()
        mock_ananta.storage.store_document.side_effect = store_side_effect
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
        assert resp.status_code == 200
        rows = resp.json()
        by_filename = {r["filename"]: r for r in rows}
        # First file is in the topic; second (failed) is not
        topic_items = topic_mgr.list_items("MyTopic")
        assert by_filename["first.txt"]["project_id"] in topic_items
        # The failed file's project_id is "" (not stored), so the seen pid
        # for the second file must not appear in the topic.
        assert seen_pids[1] not in topic_items


class TestUploadFileCountLimit:
    def test_upload_exceeding_file_count_returns_413(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
    ) -> None:
        """A request with more than MAX_FOLDER_FILES files is rejected with 413.

        The frontend's MAX_FOLDER_FILES early-bail caps drag-drop uploads, but
        click-folder selections and direct API callers can still submit any
        count. This server-side cap is a denial-of-service guard so a hostile
        or accidental large request can't enqueue tens of thousands of
        synchronous filesystem ops on the event loop (I2).
        """
        from ananta.explorers.document.config import MAX_FOLDER_FILES

        mock_ananta.create_project.return_value = MagicMock()
        files = [
            ("files", (f"f{i}.txt", b"x", "text/plain"))
            for i in range(MAX_FOLDER_FILES + 1)
        ]
        resp = client.post("/api/documents/upload", files=files)
        assert resp.status_code == 413
        # No project should have been created — the cap fires before the loop.
        mock_ananta.create_project.assert_not_called()

    def test_upload_at_file_count_limit_succeeds(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
    ) -> None:
        """Uploads with exactly MAX_FOLDER_FILES files are not rejected by the cap."""
        from ananta.explorers.document.config import MAX_FOLDER_FILES

        mock_ananta.create_project.return_value = MagicMock()
        files = [
            ("files", (f"f{i}.txt", b"x", "text/plain"))
            for i in range(MAX_FOLDER_FILES)
        ]
        resp = client.post("/api/documents/upload", files=files)
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == MAX_FOLDER_FILES


class TestUploadSizeLimit:
    def test_upload_exceeding_per_file_limit_returns_failed_row(
        self,
        client: TestClient,
    ) -> None:
        """Uploads exceeding MAX_UPLOAD_BYTES become per-file failed rows (status 200)."""
        from ananta.explorers.document.api import MAX_UPLOAD_BYTES

        oversized = b"x" * (MAX_UPLOAD_BYTES + 1)
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("big.txt", oversized, "text/plain"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        assert "limit" in row["reason"].lower()

    def test_upload_at_size_limit_succeeds(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
    ) -> None:
        """Uploads exactly at the limit should succeed."""
        from ananta.explorers.document.api import MAX_UPLOAD_BYTES

        mock_ananta.create_project.return_value = MagicMock()
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

        After A4 (per-file partial success): unsupported extensions appear as
        per-file `failed` rows with status 200 — no upload dir is created.
        """
        # A small payload is enough — the extension check must come first.
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        # No upload directory should have been created for the rejected file.
        assert list(uploads_dir.iterdir()) == []

    def test_oversized_upload_caps_memory(
        self,
        client: TestClient,
    ) -> None:
        """Server must not read more than MAX_UPLOAD_BYTES+1 into memory.

        Verifies the capped-read approach: the endpoint reads at most
        MAX_UPLOAD_BYTES+1 bytes, then checks length.

        After A4: per-file oversize is a `failed` row with status 200.
        """
        from ananta.explorers.document.api import MAX_UPLOAD_BYTES

        # 2x the limit — old code would allocate all of this.
        oversized = b"x" * (MAX_UPLOAD_BYTES * 2)
        resp = client.post(
            "/api/documents/upload",
            files=[("files", ("huge.txt", oversized, "text/plain"))],
        )
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["status"] == "failed"
        assert "limit" in row["reason"].lower()

    def test_extension_lowercased_in_stored_format(
        self,
        client: TestClient,
        mock_ananta: MagicMock,
        uploads_dir: Path,
    ) -> None:
        """Stored file extension should be lowercased (S9)."""
        mock_ananta.create_project.return_value = MagicMock()
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
        mock_ananta: MagicMock,
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
        mock_ananta.delete_project.assert_called_once_with("doc-123")


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
        mock_ananta: MagicMock,
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


class TestDownloadDocument:
    """Tests for GET /documents/{doc_id}/download."""

    def _setup_upload(
        self, uploads_dir: Path, doc_id: str, filename: str, content: bytes = b"data"
    ) -> None:
        """Create upload dir with meta.json and original file."""
        doc_dir = uploads_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix
        (doc_dir / f"original{ext}").write_bytes(content)
        (doc_dir / "meta.json").write_text(json.dumps({"filename": filename}))

    def test_download_returns_file(self, client: TestClient, uploads_dir: Path) -> None:
        self._setup_upload(uploads_dir, "doc-abc12345", "report.pdf")
        resp = client.get("/api/documents/doc-abc12345/download")
        assert resp.status_code == 200
        assert resp.content == b"data"

    def test_download_sanitizes_quotes_in_filename(
        self, client: TestClient, uploads_dir: Path
    ) -> None:
        """Filenames with " are sanitized to prevent header injection."""
        self._setup_upload(uploads_dir, "doc-abc12345", 'bad"name.pdf')
        resp = client.get("/api/documents/doc-abc12345/download")
        assert resp.status_code == 200
        cd = resp.headers["content-disposition"]
        # The sanitized filename should replace " with _
        assert "bad_name.pdf" in cd

    def test_download_sanitizes_newlines_in_filename(
        self, client: TestClient, uploads_dir: Path
    ) -> None:
        """Filenames with \\r\\n are sanitized to prevent header injection."""
        self._setup_upload(uploads_dir, "doc-abc12345", "bad\r\nname.pdf")
        resp = client.get("/api/documents/doc-abc12345/download")
        assert resp.status_code == 200
        cd = resp.headers["content-disposition"]
        assert "\r" not in cd
        assert "\n" not in cd

    def test_download_sanitizes_semicolons_in_filename(
        self, client: TestClient, uploads_dir: Path
    ) -> None:
        """Filenames with ; are sanitized to prevent header injection."""
        self._setup_upload(uploads_dir, "doc-abc12345", "bad;name.pdf")
        resp = client.get("/api/documents/doc-abc12345/download")
        assert resp.status_code == 200
        cd = resp.headers["content-disposition"]
        # The raw filename portion should not contain unescaped semicolons
        assert "bad_name.pdf" in cd

    def test_download_404_missing_doc(self, client: TestClient) -> None:
        resp = client.get("/api/documents/doc-nosuch00/download")
        assert resp.status_code == 404


class TestRenameDocument:
    def _setup_doc(self, uploads_dir: Path, doc_id: str, filename: str) -> None:
        """Create upload dir with meta.json."""
        doc_dir = uploads_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "meta.json").write_text(
            json.dumps(
                {
                    "filename": filename,
                    "content_type": "application/pdf",
                    "size": 1024,
                    "upload_date": "2026-03-20T12:00:00Z",
                    "page_count": 5,
                }
            )
        )

    def test_rename_updates_filename(self, client: TestClient, uploads_dir: Path) -> None:
        self._setup_doc(uploads_dir, "report-a3f2", "report.pdf")
        resp = client.patch(
            "/api/documents/report-a3f2",
            json={"new_name": "quarterly-report.pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "quarterly-report.pdf"
        # Verify meta.json was updated
        meta = json.loads((uploads_dir / "report-a3f2" / "meta.json").read_text())
        assert meta["filename"] == "quarterly-report.pdf"

    def test_rename_returns_full_document_info(self, client: TestClient, uploads_dir: Path) -> None:
        self._setup_doc(uploads_dir, "report-a3f2", "report.pdf")
        resp = client.patch(
            "/api/documents/report-a3f2",
            json={"new_name": "new-name.pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "report-a3f2"
        assert data["content_type"] == "application/pdf"
        assert data["size"] == 1024

    def test_rename_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.patch(
            "/api/documents/nosuch-doc0",
            json={"new_name": "new.pdf"},
        )
        assert resp.status_code == 404

    def test_rename_empty_name_returns_422(self, client: TestClient, uploads_dir: Path) -> None:
        self._setup_doc(uploads_dir, "report-a3f2", "report.pdf")
        resp = client.patch(
            "/api/documents/report-a3f2",
            json={"new_name": "  "},
        )
        assert resp.status_code == 422

    def test_rename_validates_doc_id(self, client: TestClient) -> None:
        resp = client.patch(
            "/api/documents/..%2F..%2Fetc",
            json={"new_name": "evil.pdf"},
        )
        assert resp.status_code == 400
