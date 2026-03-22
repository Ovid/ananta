"""Tests for the shared explorer launcher."""

from ananta.explorers.launcher import LauncherConfig, parse_launcher_args


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
