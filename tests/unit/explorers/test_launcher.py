"""Tests for the shared explorer launcher."""

import os
import subprocess
from unittest.mock import patch

from ananta.explorers.launcher import (
    LauncherConfig,
    check_command,
    check_docker_running,
    check_env_var,
    check_python_version,
    ensure_sandbox_image,
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


class TestCheckEnvVar:
    def test_var_set(self) -> None:
        with patch.dict(os.environ, {"ANANTA_API_KEY": "sk-test"}):
            assert check_env_var("ANANTA_API_KEY", "export ANANTA_API_KEY=<key>") is None

    def test_var_missing(self) -> None:
        env = os.environ.copy()
        env.pop("ANANTA_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            error = check_env_var("ANANTA_API_KEY", "export ANANTA_API_KEY=<key>")
            assert error is not None
            assert "ANANTA_API_KEY" in error

    def test_var_empty(self) -> None:
        with patch.dict(os.environ, {"ANANTA_API_KEY": ""}):
            error = check_env_var("ANANTA_API_KEY", "export ANANTA_API_KEY=<key>")
            assert error is not None


class TestCheckDockerRunning:
    def test_docker_running(self) -> None:
        with patch("ananta.explorers.launcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert check_docker_running() is None

    def test_docker_not_running(self) -> None:
        with patch("ananta.explorers.launcher.subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker")):
            error = check_docker_running()
            assert error is not None
            assert "Docker" in error

    def test_docker_not_installed(self) -> None:
        with patch("ananta.explorers.launcher.shutil.which", return_value=None):
            # If docker isn't on PATH, skip the check (already caught by check_command)
            assert check_docker_running() is None


class TestEnsureSandboxImage:
    def test_image_exists(self) -> None:
        with patch("ananta.explorers.launcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert ensure_sandbox_image("/project/root") is None

    def test_image_missing_build_succeeds(self, capsys: object) -> None:
        call_count = 0

        def side_effect(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # docker image inspect fails
                raise subprocess.CalledProcessError(1, "docker")
            # docker build succeeds
            return subprocess.CompletedProcess([], 0)

        with patch("ananta.explorers.launcher.subprocess.run", side_effect=side_effect):
            assert ensure_sandbox_image("/project/root") is None

    def test_image_missing_build_fails(self) -> None:
        with patch(
            "ananta.explorers.launcher.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "docker"),
        ):
            error = ensure_sandbox_image("/project/root")
            assert error is not None
            assert "sandbox" in error.lower() or "image" in error.lower()

    def test_docker_not_installed(self) -> None:
        with patch("ananta.explorers.launcher.shutil.which", return_value=None):
            assert ensure_sandbox_image("/project/root") is None
