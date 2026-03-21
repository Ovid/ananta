"""Tests for web explorer argument parsing."""

from __future__ import annotations

from ananta.experimental.web.__main__ import parse_args


class TestWebParseArgs:
    def test_defaults(self) -> None:
        args = parse_args([])
        assert args.port == 8000
        assert args.bind == "127.0.0.1"
        assert args.open is False
        assert args.model is None
        assert args.data_dir is None

    def test_custom_port(self) -> None:
        args = parse_args(["--port", "9000"])
        assert args.port == 9000

    def test_open_flag(self) -> None:
        args = parse_args(["--open"])
        assert args.open is True

    def test_model_flag(self) -> None:
        args = parse_args(["--model", "gpt-4o"])
        assert args.model == "gpt-4o"
