"""Tests for DocumentExplorerState and create_app_state."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ananta.explorers.document.dependencies import (
    DocumentExplorerState,
    create_app_state,
)
from ananta.explorers.document.topics import DocumentTopicManager
from ananta.explorers.shared_ui.session import WebConversationSession


class TestDocumentExplorerState:
    """Tests for the DocumentExplorerState dataclass."""

    def test_has_ananta_attribute(self) -> None:
        """DocumentExplorerState has an ananta attribute."""
        state = DocumentExplorerState(
            ananta=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
            extra_dirs={"uploads": Path("/tmp")},
        )
        assert hasattr(state, "ananta")

    def test_has_topic_mgr_attribute(self) -> None:
        """DocumentExplorerState has a topic_mgr attribute."""
        state = DocumentExplorerState(
            ananta=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
            extra_dirs={"uploads": Path("/tmp")},
        )
        assert hasattr(state, "topic_mgr")

    def test_has_session_attribute(self) -> None:
        """DocumentExplorerState has a session attribute."""
        state = DocumentExplorerState(
            ananta=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
            extra_dirs={"uploads": Path("/tmp")},
        )
        assert hasattr(state, "session")

    def test_has_model_attribute(self) -> None:
        """DocumentExplorerState has a model attribute."""
        state = DocumentExplorerState(
            ananta=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="gpt-5",
            extra_dirs={"uploads": Path("/tmp")},
        )
        assert state.model == "gpt-5"

    def test_has_uploads_dir_attribute(self) -> None:
        """DocumentExplorerState has an uploads_dir property."""
        state = DocumentExplorerState(
            ananta=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
            extra_dirs={"uploads": Path("/tmp/uploads")},
        )
        assert state.uploads_dir == Path("/tmp/uploads")


class TestCreateAppState:
    """Tests for create_app_state factory function."""

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_returns_document_explorer_state(
        self, mock_ananta_cls: MagicMock, tmp_path: Path
    ) -> None:
        """create_app_state returns a DocumentExplorerState instance."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state, DocumentExplorerState)

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_creates_ananta_data_dir(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates the ananta_data subdirectory."""
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "ananta_data").is_dir()

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_creates_topics_dir(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates the topics subdirectory."""
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "topics").is_dir()

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_creates_uploads_dir(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates the uploads subdirectory."""
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "uploads").is_dir()

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    @patch("ananta.explorers.shared_ui.dependencies.Path.home")
    def test_default_data_dir(
        self, mock_home: MagicMock, mock_ananta_cls: MagicMock, tmp_path: Path
    ) -> None:
        """create_app_state uses ~/.ananta/document-explorer/ as default data_dir."""
        mock_home.return_value = tmp_path
        state = create_app_state(data_dir=None)
        expected_data_dir = tmp_path / ".ananta" / "document-explorer"
        assert (expected_data_dir / "ananta_data").is_dir()
        assert (expected_data_dir / "topics").is_dir()
        assert (expected_data_dir / "uploads").is_dir()
        assert isinstance(state, DocumentExplorerState)

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_model_override(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state passes model override to config."""
        state = create_app_state(data_dir=tmp_path, model="custom-model")
        assert state.model == "custom-model"

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_state_has_topic_mgr(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates a DocumentTopicManager."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.topic_mgr, DocumentTopicManager)

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_state_has_session(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates a WebConversationSession."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.session, WebConversationSession)

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_session_project_dir_is_data_dir(
        self, mock_ananta_cls: MagicMock, tmp_path: Path
    ) -> None:
        """Session's backing file is at data_dir/conversation.json (global)."""
        state = create_app_state(data_dir=tmp_path)
        expected = tmp_path / "conversation.json"
        assert state.session._file == expected

    @patch("ananta.explorers.shared_ui.dependencies.Ananta")
    def test_uploads_dir_matches(self, mock_ananta_cls: MagicMock, tmp_path: Path) -> None:
        """State's uploads_dir points to the uploads subdirectory."""
        state = create_app_state(data_dir=tmp_path)
        assert state.uploads_dir == tmp_path / "uploads"
