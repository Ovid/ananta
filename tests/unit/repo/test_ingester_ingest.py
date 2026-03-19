"""Tests for RepoIngester.ingest() — repo file ingestion orchestration."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.exceptions import ParseError, RepoIngestError
from shesha.models import ParsedDocument
from shesha.repo.ingester import RepoIngester
from shesha.storage.filesystem import FilesystemStorage


@pytest.fixture
def ingester(tmp_path: Path) -> RepoIngester:
    return RepoIngester(storage_path=tmp_path)


@pytest.fixture
def storage(tmp_path: Path) -> FilesystemStorage:
    return FilesystemStorage(root_path=tmp_path / "storage")


@pytest.fixture
def parser_registry() -> MagicMock:
    return MagicMock()


def _make_parsed_doc(name: str, content: str = "content") -> ParsedDocument:
    return ParsedDocument(
        name=name,
        content=content,
        format="py",
        metadata={},
        char_count=len(content),
        parse_warnings=[],
    )


class TestIngestNewProject:
    """Tests for RepoIngester.ingest() creating new projects."""

    def test_ingest_new_project_parses_and_stores_files(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """ingest() creates project, parses files, stores documents."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)
        (repo_path / "main.py").write_text("print('hello')")
        (repo_path / "utils.py").write_text("def helper(): pass")

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = [
            _make_parsed_doc("main.py", "print('hello')"),
            _make_parsed_doc("utils.py", "def helper(): pass"),
        ]
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["main.py", "utils.py"])

        result = ingester.ingest(
            storage=storage,
            parser_registry=parser_registry,
            url="/fake/repo",
            name="test-project",
            path=None,
            is_update=False,
        )

        assert result.files_ingested == 2
        assert result.files_skipped == 0
        assert result.warnings == []
        assert "main.py" in storage.list_documents("test-project")
        assert "utils.py" in storage.list_documents("test-project")

    def test_ingest_skips_unparseable_files(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Files without a parser are skipped and counted."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        parser_registry.find_parser.return_value = None
        ingester.list_files_from_path = MagicMock(return_value=["binary.dat"])

        result = ingester.ingest(
            storage=storage,
            parser_registry=parser_registry,
            url="/fake/repo",
            name="test-project",
            path=None,
            is_update=False,
        )

        assert result.files_ingested == 0
        assert result.files_skipped == 1

    def test_ingest_records_parse_errors_as_warnings(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """ParseError during file parsing is recorded as a warning."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = ParseError("bad.py", "syntax error")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["bad.py"])

        result = ingester.ingest(
            storage=storage,
            parser_registry=parser_registry,
            url="/fake/repo",
            name="test-project",
            path=None,
            is_update=False,
        )

        assert result.files_ingested == 0
        assert result.files_skipped == 1
        assert len(result.warnings) == 1
        assert "bad.py" in result.warnings[0]

    def test_ingest_cleans_up_project_on_failure(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Failed new-project ingestion deletes the partially created project."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = RuntimeError("disk full")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["file.py"])

        with pytest.raises(RepoIngestError):
            ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="/fake/repo",
                name="test-project",
                path=None,
                is_update=False,
            )

        assert not storage.project_exists("test-project")

    def test_ingest_cleans_up_cloned_repo_on_failure_for_remote(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Failed remote ingestion also deletes the cloned repo directory."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = RuntimeError("disk full")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["file.py"])

        with patch.object(ingester, "delete_repo") as mock_delete:
            with pytest.raises(RepoIngestError):
                ingester.ingest(
                    storage=storage,
                    parser_registry=parser_registry,
                    url="https://github.com/org/test-project",
                    name="test-project",
                    path=None,
                    is_update=False,
                )

            mock_delete.assert_called_once_with("test-project")


class TestIngestUpdate:
    """Tests for RepoIngester.ingest() updating existing projects."""

    def test_ingest_update_uses_atomic_swap(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Update ingestion uses swap_docs for atomic replacement."""
        # Create existing project with old doc
        storage.create_project("test-project")
        storage.store_document("test-project", _make_parsed_doc("old.py", "old"))

        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = _make_parsed_doc("new.py", "new")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["new.py"])

        result = ingester.ingest(
            storage=storage,
            parser_registry=parser_registry,
            url="/fake/repo",
            name="test-project",
            path=None,
            is_update=True,
        )

        assert result.files_ingested == 1
        docs = storage.list_documents("test-project")
        assert "new.py" in docs
        assert "old.py" not in docs

    def test_ingest_update_deletes_staging_project_after_swap(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Successful update deletes the staging project after swap_docs."""
        storage.create_project("test-project")
        storage.store_document("test-project", _make_parsed_doc("old.py", "old"))

        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = _make_parsed_doc("new.py", "new")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["new.py"])

        ingester.ingest(
            storage=storage,
            parser_registry=parser_registry,
            url="/fake/repo",
            name="test-project",
            path=None,
            is_update=True,
        )

        # No _staging_* projects should remain
        all_projects = storage.list_projects()
        staging = [p for p in all_projects if p.startswith("_staging_")]
        assert staging == [], f"Orphaned staging projects: {staging}"

    def test_ingest_update_cleans_up_staging_on_failure(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Failed update ingestion deletes staging, leaves original untouched."""
        storage.create_project("test-project")
        storage.store_document("test-project", _make_parsed_doc("original.py", "safe"))

        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = RuntimeError("disk full")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["file.py"])

        with pytest.raises(RepoIngestError):
            ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="/fake/repo",
                name="test-project",
                path=None,
                is_update=True,
            )

        # Original project untouched
        assert storage.project_exists("test-project")
        assert "original.py" in storage.list_documents("test-project")

    def test_ingest_update_calls_swap_docs(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """Update ingestion calls storage.swap_docs (not hasattr check)."""
        storage.create_project("test-project")
        storage.store_document("test-project", _make_parsed_doc("old.py", "old"))

        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = _make_parsed_doc("new.py", "new")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["new.py"])

        with patch.object(storage, "swap_docs", wraps=storage.swap_docs) as mock_swap:
            result = ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="/fake/repo",
                name="test-project",
                path=None,
                is_update=True,
            )

            mock_swap.assert_called_once()
            assert result.files_ingested == 1


class TestIngestUpdateStagingCleanupFailure:
    """Tests that staging cleanup failure after swap doesn't block metadata save."""

    def test_staging_cleanup_failure_still_saves_sha(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """When staging delete fails after successful swap, SHA is still saved."""
        storage.create_project("test-project")
        storage.store_document("test-project", _make_parsed_doc("old.py", "old"))

        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = _make_parsed_doc("new.py", "new")
        parser_registry.find_parser.return_value = mock_parser
        ingester.list_files_from_path = MagicMock(return_value=["new.py"])

        original_delete = storage.delete_project

        def failing_delete(name: str) -> None:
            if name.startswith("_staging_"):
                raise OSError("disk error during cleanup")
            original_delete(name)

        with (
            patch.object(storage, "delete_project", side_effect=failing_delete),
            patch.object(ingester, "get_sha_from_path", return_value="abc123"),
        ):
            result = ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="https://github.com/org/repo",
                name="test-project",
                path=None,
                is_update=True,
            )

        # Swap succeeded — docs should be updated
        assert result.files_ingested == 1
        # SHA must be saved despite cleanup failure
        assert ingester.get_saved_sha("test-project") == "abc123"
        # Source URL must be saved despite cleanup failure
        assert ingester.get_source_url("test-project") == "https://github.com/org/repo"


class TestIngestSavesMetadata:
    """Tests that ingest() persists SHA and source URL."""

    def test_ingest_saves_sha(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """ingest() saves the repo SHA after successful ingestion."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        parser_registry.find_parser.return_value = None
        ingester.list_files_from_path = MagicMock(return_value=[])

        with patch.object(ingester, "get_sha_from_path", return_value="abc123"):
            ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="/fake/repo",
                name="test-project",
                path=None,
                is_update=False,
            )

        assert ingester.get_saved_sha("test-project") == "abc123"

    def test_ingest_succeeds_when_save_sha_fails(
        self,
        ingester: RepoIngester,
        storage: FilesystemStorage,
        parser_registry: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Metadata save failure after successful ingest must not propagate."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        parser_registry.find_parser.return_value = None
        ingester.list_files_from_path = MagicMock(return_value=[])

        with (
            patch.object(ingester, "get_sha_from_path", return_value="abc123"),
            patch.object(ingester, "save_sha", side_effect=OSError("disk full")),
            caplog.at_level(logging.WARNING),
        ):
            result = ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="/fake/repo",
                name="test-project",
                path=None,
                is_update=False,
            )

        # Ingest must still succeed
        assert result.files_ingested == 0
        assert "disk full" in caplog.text

    def test_ingest_succeeds_when_save_source_url_fails(
        self,
        ingester: RepoIngester,
        storage: FilesystemStorage,
        parser_registry: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Source URL save failure after successful ingest must not propagate."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        parser_registry.find_parser.return_value = None
        ingester.list_files_from_path = MagicMock(return_value=[])

        with (
            patch.object(ingester, "get_sha_from_path", return_value=None),
            patch.object(ingester, "save_source_url", side_effect=OSError("permission denied")),
            caplog.at_level(logging.WARNING),
        ):
            result = ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="https://github.com/org/repo",
                name="test-project",
                path=None,
                is_update=False,
            )

        assert result.files_ingested == 0
        assert "permission denied" in caplog.text

    def test_ingest_saves_source_url(
        self, ingester: RepoIngester, storage: FilesystemStorage, parser_registry: MagicMock
    ):
        """ingest() saves the source URL for later retrieval."""
        repo_path = ingester.repos_dir / "test-project"
        repo_path.mkdir(parents=True)

        parser_registry.find_parser.return_value = None
        ingester.list_files_from_path = MagicMock(return_value=[])

        with patch.object(ingester, "get_sha_from_path", return_value=None):
            ingester.ingest(
                storage=storage,
                parser_registry=parser_registry,
                url="https://github.com/org/test-project",
                name="test-project",
                path=None,
                is_update=False,
            )

        assert ingester.get_source_url("test-project") == "https://github.com/org/test-project"
