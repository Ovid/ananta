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

    def test_default_bind_is_localhost(self) -> None:
        args = parse_args([])
        assert args.bind == "127.0.0.1"

    def test_custom_bind(self) -> None:
        args = parse_args(["--bind", "0.0.0.0"])
        assert args.bind == "0.0.0.0"


class TestMain:
    @patch("shesha.experimental.document_explorer.__main__.parse_args")
    @patch("shesha.experimental.document_explorer.__main__.uvicorn")
    @patch("shesha.experimental.document_explorer.__main__.create_api")
    @patch("shesha.experimental.document_explorer.__main__.create_app_state")
    def test_creates_state_with_args(
        self,
        mock_state: MagicMock,
        mock_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse: MagicMock,
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
        self,
        mock_state: MagicMock,
        mock_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        mock_parse.return_value = parse_args(["--port", "9999", "--no-browser"])
        mock_state.return_value = MagicMock()
        sentinel = MagicMock(name="app")
        mock_api.return_value = sentinel
        main()
        mock_uvicorn.run.assert_called_once_with(sentinel, host="127.0.0.1", port=9999)
