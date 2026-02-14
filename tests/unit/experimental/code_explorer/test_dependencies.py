"""Tests for code explorer dependencies (CodeExplorerState + create_app_state)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from shesha.experimental.code_explorer.dependencies import (
    CodeExplorerState,
    create_app_state,
)
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.session import WebConversationSession


class TestCodeExplorerState:
    """Tests for the CodeExplorerState dataclass."""

    def test_has_shesha_attribute(self) -> None:
        """CodeExplorerState has a shesha attribute."""
        state = CodeExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "shesha")

    def test_has_topic_mgr_attribute(self) -> None:
        """CodeExplorerState has a topic_mgr attribute."""
        state = CodeExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "topic_mgr")

    def test_has_session_attribute(self) -> None:
        """CodeExplorerState has a session attribute."""
        state = CodeExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "session")

    def test_has_model_attribute(self) -> None:
        """CodeExplorerState has a model attribute."""
        state = CodeExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert state.model == "test-model"


class TestCreateAppState:
    """Tests for create_app_state factory function."""

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_returns_code_explorer_state(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state returns a CodeExplorerState instance."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state, CodeExplorerState)

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_creates_shesha_data_dir(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates the shesha_data subdirectory."""
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "shesha_data").is_dir()

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_creates_topics_dir(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates the topics subdirectory."""
        create_app_state(data_dir=tmp_path)
        assert (tmp_path / "topics").is_dir()

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    @patch("shesha.experimental.code_explorer.dependencies.Path.home")
    def test_default_data_dir(self, mock_home: MagicMock, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state uses ~/.shesha/code-explorer/ as default data_dir."""
        mock_home.return_value = tmp_path
        state = create_app_state(data_dir=None)
        expected_data_dir = tmp_path / ".shesha" / "code-explorer"
        assert (expected_data_dir / "shesha_data").is_dir()
        assert (expected_data_dir / "topics").is_dir()
        assert isinstance(state, CodeExplorerState)

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_model_override(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state passes model override to config."""
        state = create_app_state(data_dir=tmp_path, model="custom-model")
        assert state.model == "custom-model"

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_state_has_topic_mgr(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates a CodeExplorerTopicManager."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.topic_mgr, CodeExplorerTopicManager)

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_state_has_session(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        """create_app_state creates a WebConversationSession."""
        state = create_app_state(data_dir=tmp_path)
        assert isinstance(state.session, WebConversationSession)

    @patch("shesha.experimental.code_explorer.dependencies.Shesha")
    def test_session_project_dir_is_data_dir(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        """Session's backing file is at data_dir/conversation.json (global)."""
        state = create_app_state(data_dir=tmp_path)
        expected = tmp_path / "conversation.json"
        assert state.session._file == expected
