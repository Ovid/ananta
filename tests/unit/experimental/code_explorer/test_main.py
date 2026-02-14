"""Tests for code explorer __main__.py entry point."""

from __future__ import annotations

from shesha.experimental.code_explorer.__main__ import parse_args


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
