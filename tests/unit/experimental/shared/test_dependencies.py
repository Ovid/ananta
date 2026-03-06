"""Tests for shared explorer dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.experimental.shared.dependencies import (
    BaseExplorerState,
    create_app_state,
    get_topic_session,
)
from shesha.experimental.shared.session import WebConversationSession
from shesha.experimental.shared.topics import BaseTopicManager


class TestBaseExplorerState:
    def test_has_shesha_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "shesha")

    def test_has_topic_mgr_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "topic_mgr")

    def test_has_session_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "session")

    def test_has_model_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="gpt-5",
        )
        assert state.model == "gpt-5"


class TestCreateAppState:
    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_returns_base_explorer_state(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state, BaseExplorerState)

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_shesha_data_dir(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert (tmp_path / "shesha_data").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_topics_dir(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert (tmp_path / "topics").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_extra_dirs(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
            extra_dirs={"uploads": "uploads"},
        )
        assert (tmp_path / "uploads").is_dir()
        assert state.extra_dirs["uploads"] == tmp_path / "uploads"

    @patch("shesha.experimental.shared.dependencies.Shesha")
    @patch("shesha.experimental.shared.dependencies.Path.home")
    def test_default_data_dir(
        self, mock_home: MagicMock, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_home.return_value = tmp_path
        create_app_state(
            app_name="my-explorer",
            topic_mgr_class=BaseTopicManager,
        )
        expected = tmp_path / ".shesha" / "my-explorer"
        assert (expected / "shesha_data").is_dir()
        assert (expected / "topics").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_model_override(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
            model="custom-model",
        )
        assert state.model == "custom-model"

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_state_has_topic_mgr(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state.topic_mgr, BaseTopicManager)

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_state_has_session(self, mock_shesha_cls: MagicMock, tmp_path: Path) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state.session, WebConversationSession)


class TestGetTopicSession:
    def test_returns_session_for_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path / "topics")
        mgr.create("Research")
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=mgr,
            session=MagicMock(),
            model="test",
        )
        session = get_topic_session(state, "Research")
        assert isinstance(session, WebConversationSession)

    def test_raises_for_nonexistent_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path / "topics")
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=mgr,
            session=MagicMock(),
            model="test",
        )
        with pytest.raises(ValueError, match="Topic not found"):
            get_topic_session(state, "Nonexistent")
