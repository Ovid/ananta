"""Tests for Project class."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ananta.exceptions import EngineNotConfiguredError
from ananta.models import ParsedDocument
from ananta.project import Project
from ananta.rlm.trace import StepType, TokenUsage


@pytest.fixture
def mock_storage() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock()
    parser = MagicMock()
    parser.parse.return_value = ParsedDocument(
        name="test.txt",
        content="content",
        format="txt",
        metadata={},
        char_count=7,
        parse_warnings=[],
    )
    registry.find_parser.return_value = parser
    return registry


class TestProject:
    """Tests for Project."""

    def test_upload_file(self, mock_storage: MagicMock, mock_registry: MagicMock, tmp_path: Path):
        """Upload parses and stores a file."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        project.upload(test_file)

        mock_storage.store_document.assert_called_once()

    def test_list_documents(self, mock_storage: MagicMock, mock_registry: MagicMock):
        """List documents returns storage list."""
        mock_storage.list_documents.return_value = ["a.txt", "b.txt"]

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        docs = project.list_documents()

        assert docs == ["a.txt", "b.txt"]

    def test_delete_document(self, mock_storage: MagicMock, mock_registry: MagicMock):
        """Delete document calls storage."""
        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        project.delete_document("old.txt")

        mock_storage.delete_document.assert_called_with("test-project", "old.txt")

    def test_query_without_engine_raises_engine_not_configured(
        self, mock_storage: MagicMock, mock_registry: MagicMock
    ):
        """Query with no engine raises EngineNotConfiguredError."""
        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )

        with pytest.raises(EngineNotConfiguredError):
            project.query("test question")

    def test_query_passes_on_progress_to_engine(
        self, mock_storage: MagicMock, mock_registry: MagicMock
    ):
        """Query passes on_progress callback and documents to RLM engine."""
        # Mock the engine
        mock_engine = MagicMock()
        mock_engine.query.return_value = MagicMock(answer="test answer")

        # Mock storage.load_all_documents to return real document objects
        mock_storage.load_all_documents.return_value = [
            ParsedDocument(
                name="doc.txt",
                content="doc content",
                format="txt",
                metadata={},
                char_count=11,
                parse_warnings=[],
            )
        ]

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
            rlm_engine=mock_engine,
        )

        # Create a callback
        def on_progress(
            step_type: StepType, iteration: int, content: str, token_usage: "TokenUsage"
        ) -> None:
            pass

        project.query("test question", on_progress=on_progress)

        # Verify load_all_documents was called with project_id
        mock_storage.load_all_documents.assert_called_once_with("test-project")

        # Verify engine.query received correct arguments
        mock_engine.query.assert_called_once()
        call_kwargs = mock_engine.query.call_args.kwargs
        assert call_kwargs.get("on_progress") is on_progress
        assert call_kwargs.get("documents") == ["doc content"]
        assert call_kwargs.get("doc_names") == ["doc.txt"]
        assert call_kwargs.get("question") == "test question"

    def test_upload_directory_uses_relative_paths_for_doc_names(
        self, mock_storage: MagicMock, tmp_path: Path
    ):
        """Upload directory sets doc.name to relative path, not basename."""
        # Create nested files with same basename in different subdirectories
        (tmp_path / "src" / "foo").mkdir(parents=True)
        (tmp_path / "src" / "bar").mkdir(parents=True)
        (tmp_path / "src" / "foo" / "main.py").write_text("# foo")
        (tmp_path / "src" / "bar" / "main.py").write_text("# bar")

        # Set up parser that returns basename as name (current behavior)
        parser = MagicMock()
        parser.parse.side_effect = lambda path, **kwargs: ParsedDocument(
            name=path.name,
            content=path.read_text(),
            format="py",
            metadata={},
            char_count=5,
            parse_warnings=[],
        )
        registry = MagicMock()
        registry.find_parser.return_value = parser

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=registry,
        )
        uploaded = project.upload(tmp_path, recursive=True)

        # Both files should be stored with distinct relative paths
        assert len(uploaded) == 2
        stored_names = [call.args[1].name for call in mock_storage.store_document.call_args_list]
        assert "src/foo/main.py" in stored_names
        assert "src/bar/main.py" in stored_names

    def test_upload_single_file_keeps_basename(
        self, mock_storage: MagicMock, mock_registry: MagicMock, tmp_path: Path
    ):
        """Upload single file keeps basename as doc.name."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        project.upload(test_file)

        stored_doc = mock_storage.store_document.call_args.args[1]
        assert stored_doc.name == "test.txt"

    def test_query_passes_storage_to_engine(
        self, mock_storage: MagicMock, mock_registry: MagicMock
    ):
        """Query always passes storage to engine regardless of backend type."""
        mock_engine = MagicMock()
        mock_engine.query.return_value = MagicMock(answer="test answer")

        mock_storage.load_all_documents.return_value = [
            ParsedDocument(
                name="doc.txt",
                content="doc content",
                format="txt",
                metadata={},
                char_count=11,
                parse_warnings=[],
            )
        ]

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
            rlm_engine=mock_engine,
        )

        project.query("test question")

        call_kwargs = mock_engine.query.call_args.kwargs
        assert call_kwargs.get("storage") is mock_storage
        assert call_kwargs.get("project_id") == "test-project"


class TestProjectPublicAPI:
    def test_rlm_engine_property_returns_engine(
        self, mock_storage: MagicMock, mock_registry: MagicMock
    ) -> None:
        engine = MagicMock()
        project = Project(
            project_id="test",
            storage=mock_storage,
            parser_registry=mock_registry,
            rlm_engine=engine,
        )
        assert project.rlm_engine is engine

    def test_rlm_engine_property_returns_none_when_not_set(
        self, mock_storage: MagicMock, mock_registry: MagicMock
    ) -> None:
        project = Project(
            project_id="test",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        assert project.rlm_engine is None
