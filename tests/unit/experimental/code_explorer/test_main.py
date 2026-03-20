"""Tests for code explorer __main__.py entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ananta.experimental.code_explorer.__main__ import main, parse_args


class TestParseArgs:
    """Tests for argument parsing."""

    def test_default_port(self) -> None:
        """Default port is 8001."""
        args = parse_args([])
        assert args.port == 8001

    def test_custom_port(self) -> None:
        """--port overrides the default."""
        args = parse_args(["--port", "9000"])
        assert args.port == 9000

    def test_default_data_dir_is_none(self) -> None:
        """Default data-dir is None."""
        args = parse_args([])
        assert args.data_dir is None

    def test_custom_data_dir(self) -> None:
        """--data-dir sets the data directory."""
        args = parse_args(["--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"

    def test_no_browser_flag(self) -> None:
        """--no-browser sets the flag to True."""
        args = parse_args(["--no-browser"])
        assert args.no_browser is True

    def test_no_browser_default(self) -> None:
        """Default no-browser is False."""
        args = parse_args([])
        assert args.no_browser is False

    def test_default_model_is_none(self) -> None:
        """Default model is None."""
        args = parse_args([])
        assert args.model is None

    def test_custom_model(self) -> None:
        """--model sets the model."""
        args = parse_args(["--model", "gpt-4o"])
        assert args.model == "gpt-4o"

    def test_default_bind_is_localhost(self) -> None:
        """Default bind address is 127.0.0.1."""
        args = parse_args([])
        assert args.bind == "127.0.0.1"

    def test_custom_bind(self) -> None:
        """--bind overrides the default."""
        args = parse_args(["--bind", "0.0.0.0"])
        assert args.bind == "0.0.0.0"


class TestMain:
    """Tests for main() startup logic."""

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    def test_creates_app_state_with_args(
        self,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() passes data_dir and model to create_app_state."""
        mock_parse_args.return_value = parse_args(
            ["--data-dir", "/tmp/data", "--model", "gpt-4o", "--no-browser"]
        )
        mock_create_state.return_value = MagicMock()
        mock_create_api.return_value = MagicMock()

        main()

        mock_create_state.assert_called_once_with(data_dir=Path("/tmp/data"), model="gpt-4o")

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    def test_creates_app_state_none_data_dir(
        self,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() passes None data_dir when --data-dir not specified."""
        mock_parse_args.return_value = parse_args(["--no-browser"])
        mock_create_state.return_value = MagicMock()
        mock_create_api.return_value = MagicMock()

        main()

        mock_create_state.assert_called_once_with(data_dir=None, model=None)

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    def test_creates_api_with_state(
        self,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() passes the state to create_api."""
        mock_parse_args.return_value = parse_args(["--no-browser"])
        sentinel_state = MagicMock(name="state")
        mock_create_state.return_value = sentinel_state
        mock_create_api.return_value = MagicMock()

        main()

        mock_create_api.assert_called_once_with(sentinel_state)

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    def test_runs_uvicorn_with_app_host_port(
        self,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() calls uvicorn.run with the app, host, and port."""
        mock_parse_args.return_value = parse_args(["--port", "9999", "--no-browser"])
        mock_create_state.return_value = MagicMock()
        sentinel_app = MagicMock(name="app")
        mock_create_api.return_value = sentinel_app

        main()

        mock_uvicorn.run.assert_called_once_with(sentinel_app, host="127.0.0.1", port=9999)

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    @patch("ananta.experimental.code_explorer.__main__.threading")
    @patch("ananta.experimental.code_explorer.__main__.webbrowser")
    def test_opens_browser_when_no_browser_not_set(
        self,
        mock_webbrowser: MagicMock,
        mock_threading: MagicMock,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() starts a timer to open the browser when --no-browser is not set."""
        mock_parse_args.return_value = parse_args(["--port", "8001"])
        mock_create_state.return_value = MagicMock()
        mock_create_api.return_value = MagicMock()
        mock_timer = MagicMock()
        mock_threading.Timer.return_value = mock_timer

        main()

        mock_threading.Timer.assert_called_once()
        mock_timer.start.assert_called_once()

    @patch("ananta.experimental.code_explorer.__main__.parse_args")
    @patch("ananta.experimental.code_explorer.__main__.uvicorn")
    @patch("ananta.experimental.code_explorer.__main__.create_api")
    @patch("ananta.experimental.code_explorer.__main__.create_app_state")
    @patch("ananta.experimental.code_explorer.__main__.threading")
    def test_no_browser_when_flag_set(
        self,
        mock_threading: MagicMock,
        mock_create_state: MagicMock,
        mock_create_api: MagicMock,
        mock_uvicorn: MagicMock,
        mock_parse_args: MagicMock,
    ) -> None:
        """main() does NOT open browser when --no-browser is set."""
        mock_parse_args.return_value = parse_args(["--no-browser"])
        mock_create_state.return_value = MagicMock()
        mock_create_api.return_value = MagicMock()

        main()

        mock_threading.Timer.assert_not_called()
