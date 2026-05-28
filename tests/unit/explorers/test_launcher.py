"""Tests for the shared explorer launcher."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from ananta.config import DEFAULT_SANDBOX_IMAGE
from ananta.explorers.launcher import (
    LauncherConfig,
    build_frontend,
    check_command,
    check_docker_running,
    check_env_var,
    check_python_version,
    ensure_sandbox_image,
    launch,
    parse_launcher_args,
    run_preflight,
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


class TestExplorerConfigs:
    """Verify per-explorer launch.py configs are consistent with their frontends."""

    def test_shared_ui_dependency_requires_shared_frontend_dir(self) -> None:
        """If a frontend's package.json depends on @ananta/shared-ui,
        the launch.py config must set shared_frontend_dir."""
        import ast
        import json

        project_root = Path(__file__).resolve().parents[3]
        launch_files = sorted(project_root.glob("*-explorer/launch.py"))
        assert launch_files, "Expected at least one explorer launch.py"

        for launch_file in launch_files:
            explorer_name = launch_file.parent.name
            tree = ast.parse(launch_file.read_text())

            # Find the LauncherConfig(...) call
            config_call = None
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "LauncherConfig"
                ):
                    config_call = node
                    break
            assert config_call is not None, f"{explorer_name}: no LauncherConfig call found"

            # Extract frontend_dir and shared_frontend_dir from the config
            kwargs = {kw.arg: kw.value for kw in config_call.keywords}
            assert "frontend_dir" in kwargs, f"{explorer_name}: missing frontend_dir"
            frontend_dir = ast.literal_eval(kwargs["frontend_dir"])
            has_shared = (
                "shared_frontend_dir" in kwargs and kwargs["shared_frontend_dir"] is not None
            )

            # Check if package.json has @ananta/shared-ui dependency
            pkg_json = project_root / frontend_dir / "package.json"
            if pkg_json.exists():
                pkg_data = json.loads(pkg_json.read_text())
                deps = pkg_data.get("dependencies", {})
                needs_shared = "@ananta/shared-ui" in deps
                assert has_shared == needs_shared, (
                    f"{explorer_name}: package.json "
                    f"{'has' if needs_shared else 'lacks'} @ananta/shared-ui dep "
                    f"but config {'sets' if has_shared else 'omits'} shared_frontend_dir"
                )


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

    def test_rebuild_equals_true(self) -> None:
        rebuild, passthrough = parse_launcher_args(["--rebuild=true", "--port", "9000"])
        assert rebuild is True
        assert passthrough == ["--port", "9000"]


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
    @patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")
    def test_docker_running(self, _mock_which: object) -> None:
        with patch("ananta.explorers.launcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert check_docker_running() is None

    @patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")
    def test_docker_not_running(self, _mock_which: object) -> None:
        side_effect = subprocess.CalledProcessError(1, "docker")
        with patch("ananta.explorers.launcher.subprocess.run", side_effect=side_effect):
            error = check_docker_running()
            assert error is not None
            assert "Docker" in error

    def test_docker_not_installed(self) -> None:
        with patch("ananta.explorers.launcher.shutil.which", return_value=None):
            # If docker isn't on PATH, skip the check (already caught by check_command)
            assert check_docker_running() is None


class TestEnsureSandboxImage:
    def test_default_matches_anantaconfig(self) -> None:
        """The launcher's fallback image name must equal AnantaConfig.sandbox_image
        so the launcher builds the same image the engine will look for."""
        from ananta.config import AnantaConfig
        from ananta.explorers import launcher

        assert launcher.DEFAULT_SANDBOX_IMAGE == AnantaConfig.sandbox_image
        assert launcher.DEFAULT_SANDBOX_IMAGE == DEFAULT_SANDBOX_IMAGE

    @patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")
    def test_image_exists(self, _mock_which: object) -> None:
        with patch("ananta.explorers.launcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert ensure_sandbox_image("/project/root") is None

    @patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")
    def test_image_missing_build_succeeds(self, _mock_which: object, capsys: object) -> None:
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

    @patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")
    def test_image_missing_build_fails(self, _mock_which: object) -> None:
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


class TestRunPreflight:
    def _make_config(self, requires_git: bool = False) -> LauncherConfig:
        return LauncherConfig(
            app_name="Test App",
            entry_point="test-app",
            frontend_dir="src/test/frontend",
            requires_git=requires_git,
        )

    @patch("ananta.explorers.launcher.check_command", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    def test_all_pass(self, *mocks: object) -> None:
        errors = run_preflight(self._make_config(), "/project")
        assert errors == []

    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_command")
    def test_collects_errors(self, mock_cmd: object, *mocks: object) -> None:
        mock_cmd.side_effect = lambda cmd, hint: (
            f"  - missing {cmd}" if cmd in ("node", "npm") else None
        )
        errors = run_preflight(self._make_config(), "/project")
        assert len(errors) == 2
        assert "node" in errors[0]
        assert "npm" in errors[1]

    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_command", return_value=None)
    def test_git_checked_when_required(self, mock_cmd: object, *mocks: object) -> None:
        """When requires_git=True, git is in the check_command call list."""
        config = self._make_config(requires_git=True)
        run_preflight(config, "/project")
        cmd_names = [call.args[0] for call in mock_cmd.call_args_list]  # type: ignore[attr-defined]
        assert "git" in cmd_names

    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_command", return_value=None)
    def test_git_not_checked_when_not_required(self, mock_cmd: object, *mocks: object) -> None:
        config = self._make_config(requires_git=False)
        run_preflight(config, "/project")
        cmd_names = [call.args[0] for call in mock_cmd.call_args_list]  # type: ignore[attr-defined]
        assert "git" not in cmd_names

    @patch("ananta.explorers.launcher.ensure_sandbox_image")
    @patch(
        "ananta.explorers.launcher.check_docker_running",
        return_value="  - Start Docker daemon (e.g. open Docker Desktop)",
    )
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_command", return_value=None)
    def test_sandbox_image_skipped_when_docker_not_running(
        self,
        mock_cmd: object,
        mock_py: object,
        mock_env: object,
        mock_docker: object,
        mock_image: object,
    ) -> None:
        """When Docker daemon is not running, ensure_sandbox_image should not be called."""
        run_preflight(self._make_config(), "/project")
        mock_image.assert_not_called()  # type: ignore[attr-defined]


class TestBuildFrontend:
    def _make_config(
        self,
        frontend_dir: str = "src/test/frontend",
        shared_frontend_dir: str | None = None,
    ) -> LauncherConfig:
        return LauncherConfig(
            app_name="Test App",
            entry_point="test-app",
            frontend_dir=frontend_dir,
            shared_frontend_dir=shared_frontend_dir,
        )

    @patch("ananta.explorers.launcher.subprocess.run")
    def test_build_when_dist_missing(self, mock_run: object, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        config = self._make_config(frontend_dir=str(frontend))
        build_frontend(config, str(tmp_path), rebuild=False)
        # Should have called npm install + npm run build
        assert mock_run.call_count == 2  # type: ignore[attr-defined]

    @patch("ananta.explorers.launcher.subprocess.run")
    def test_skip_when_dist_exists(self, mock_run: object, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "dist").mkdir()
        config = self._make_config(frontend_dir=str(frontend))
        build_frontend(config, str(tmp_path), rebuild=False)
        mock_run.assert_not_called()  # type: ignore[attr-defined]

    @patch("ananta.explorers.launcher.subprocess.run")
    def test_rebuild_forces_build(self, mock_run: object, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "dist").mkdir()
        config = self._make_config(frontend_dir=str(frontend))
        build_frontend(config, str(tmp_path), rebuild=True)
        assert mock_run.call_count == 2  # type: ignore[attr-defined]

    @patch("ananta.explorers.launcher.subprocess.run")
    def test_shared_frontend_installed(self, mock_run: object, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        shared = tmp_path / "shared"
        shared.mkdir()
        config = self._make_config(
            frontend_dir=str(frontend),
            shared_frontend_dir=str(shared),
        )
        build_frontend(config, str(tmp_path), rebuild=False)
        # shared npm install + frontend npm install + npm run build = 3
        assert mock_run.call_count == 3  # type: ignore[attr-defined]


class TestLaunch:
    def _make_config(self) -> LauncherConfig:
        return LauncherConfig(
            app_name="Test App",
            entry_point="test-app",
            frontend_dir="src/test/frontend",
        )

    @patch("ananta.explorers.launcher.subprocess.run")
    @patch("ananta.explorers.launcher.build_frontend")
    @patch("ananta.explorers.launcher.run_preflight", return_value=[])
    def test_launch_success(
        self,
        mock_preflight: object,
        mock_build: object,
        mock_run: object,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        config = self._make_config()
        exit_code = launch(config, argv=["--port", "9000"], project_root="/project")
        assert exit_code == 0
        mock_run.assert_called_once()  # type: ignore[attr-defined]
        call_args = mock_run.call_args  # type: ignore[attr-defined]
        assert call_args[0][0] == ["test-app", "--port", "9000"]

    @patch("ananta.explorers.launcher.build_frontend")
    @patch("ananta.explorers.launcher.run_preflight", return_value=["  - missing node"])
    def test_launch_preflight_failure(
        self,
        mock_preflight: object,
        mock_build: object,
    ) -> None:
        config = self._make_config()
        exit_code = launch(config, argv=[], project_root="/project")
        assert exit_code == 1
        mock_build.assert_not_called()  # type: ignore[attr-defined]

    @patch("ananta.explorers.launcher.subprocess.run")
    @patch("ananta.explorers.launcher.build_frontend")
    @patch("ananta.explorers.launcher.run_preflight", return_value=[])
    def test_rebuild_passed_to_build(
        self,
        mock_preflight: object,
        mock_build: object,
        mock_run: object,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        config = self._make_config()
        launch(config, argv=["--rebuild", "--open"], project_root="/project")
        mock_build.assert_called_once()  # type: ignore[attr-defined]
        _, kwargs = mock_build.call_args  # type: ignore[attr-defined]
        assert kwargs["rebuild"] is True
        # --rebuild should NOT be passed to the entry point
        call_args = mock_run.call_args  # type: ignore[attr-defined]
        assert "--rebuild" not in call_args[0][0]
        assert "--open" in call_args[0][0]

    @patch("ananta.explorers.launcher.build_frontend")
    @patch("ananta.explorers.launcher.run_preflight", return_value=[])
    def test_launch_build_failure_returns_exit_code_1(
        self,
        mock_preflight: object,
        mock_build: object,
    ) -> None:
        mock_build.side_effect = subprocess.CalledProcessError(1, "npm")  # type: ignore[attr-defined]
        config = self._make_config()
        exit_code = launch(config, argv=[], project_root="/project")
        assert exit_code == 1

    @patch("ananta.explorers.launcher.subprocess.run")
    @patch("ananta.explorers.launcher.build_frontend")
    @patch("ananta.explorers.launcher.run_preflight", return_value=[])
    def test_launch_missing_entry_point_returns_exit_code_1(
        self,
        mock_preflight: object,
        mock_build: object,
        mock_run: object,
    ) -> None:
        mock_run.side_effect = FileNotFoundError("No such file: 'test-app'")  # type: ignore[attr-defined]
        config = self._make_config()
        exit_code = launch(config, argv=[], project_root="/project")
        assert exit_code == 1
