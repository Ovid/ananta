"""Tests for the shared explorer launcher."""

from unittest.mock import patch

from ananta.explorers.launcher import (
    LauncherConfig,
    check_command,
    check_python_version,
    parse_launcher_args,
)


class TestLauncherConfig:
    def test_required_fields(self) -> None:
        config = LauncherConfig(
            app_name="Test App",
            entry_point="test-app",
            frontend_dir="src/ananta/explorers/test/frontend",
        )
        assert config.app_name == "Test App"
        assert config.entry_point == "test-app"
        assert config.frontend_dir == "src/ananta/explorers/test/frontend"
        assert config.requires_git is False
        assert config.shared_frontend_dir is None


class TestParseLauncherArgs:
    def test_no_args(self) -> None:
        rebuild, passthrough = parse_launcher_args([])
        assert rebuild is False
        assert passthrough == []

    def test_rebuild_stripped(self) -> None:
        rebuild, passthrough = parse_launcher_args(["--rebuild", "--port", "9000"])
        assert rebuild is True
        assert passthrough == ["--port", "9000"]

    def test_passthrough_preserved(self) -> None:
        rebuild, passthrough = parse_launcher_args(
            ["--port", "8080", "--open", "--model", "gpt-4o"]
        )
        assert rebuild is False
        assert passthrough == ["--port", "8080", "--open", "--model", "gpt-4o"]

    def test_rebuild_only(self) -> None:
        rebuild, passthrough = parse_launcher_args(["--rebuild"])
        assert rebuild is True
        assert passthrough == []


class TestCheckCommand:
    def test_command_found(self) -> None:
        with patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/python3"):
            assert check_command("python3", "https://python.org") is None

    def test_command_missing(self) -> None:
        with patch("ananta.explorers.launcher.shutil.which", return_value=None):
            error = check_command("python3", "https://python.org")
            assert error is not None
            assert "python3" in error
            assert "https://python.org" in error


class TestCheckPythonVersion:
    def test_version_ok(self) -> None:
        with patch("ananta.explorers.launcher.sys.version_info", (3, 12, 0)):
            assert check_python_version() is None

    def test_version_exactly_3_11(self) -> None:
        with patch("ananta.explorers.launcher.sys.version_info", (3, 11, 0)):
            assert check_python_version() is None

    def test_version_too_old(self) -> None:
        with patch("ananta.explorers.launcher.sys.version_info", (3, 10, 5)):
            error = check_python_version()
            assert error is not None
            assert "3.11" in error
