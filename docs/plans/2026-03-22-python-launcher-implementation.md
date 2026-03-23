# Python Launcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace bash launcher scripts and `scripts/common.sh` with testable Python: a shared `launcher.py` module and thin per-explorer `launch.py` configs, keeping bash shims only for venv bootstrapping.

**Architecture:** Each explorer directory keeps a ~20-line bash shim (venv + pip install only). A `launch.py` in each directory defines a `LauncherConfig` dataclass and calls `launch()` from `src/ananta/explorers/launcher.py`, which handles preflight checks, frontend build, and process launch via `subprocess.run()`.

**Tech Stack:** Python 3.11+, `subprocess`, `shutil.which`, `dataclasses`, pytest

**Design doc:** `docs/plans/2026-03-22-python-launcher-design.md`

---

### Task 1: LauncherConfig dataclass and arg parsing

**Files:**
- Create: `src/ananta/explorers/launcher.py`
- Create: `tests/unit/explorers/test_launcher.py`

**Step 1: Write the failing test for LauncherConfig**

```python
"""Tests for the shared explorer launcher."""

from ananta.explorers.launcher import LauncherConfig


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/explorers/test_launcher.py::TestLauncherConfig::test_required_fields -v`
Expected: FAIL — `ImportError: cannot import name 'LauncherConfig'`

**Step 3: Write the failing test for parse_launcher_args**

Add to `tests/unit/explorers/test_launcher.py`:

```python
from ananta.explorers.launcher import parse_launcher_args


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
```

**Step 4: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_launcher_args'`

**Step 5: Write minimal implementation**

Create `src/ananta/explorers/launcher.py`:

```python
"""Shared launcher logic for Ananta explorer applications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LauncherConfig:
    """Per-explorer configuration for the shared launcher."""

    app_name: str
    entry_point: str
    frontend_dir: str
    requires_git: bool = False
    shared_frontend_dir: str | None = None


def parse_launcher_args(argv: list[str]) -> tuple[bool, list[str]]:
    """Strip --rebuild from argv, return (rebuild, passthrough_args)."""
    rebuild = False
    passthrough: list[str] = []
    for arg in argv:
        if arg == "--rebuild":
            rebuild = True
        else:
            passthrough.append(arg)
    return rebuild, passthrough
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py -v`
Expected: all PASS

**Step 7: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add LauncherConfig dataclass and arg parsing for explorer launcher"
```

---

### Task 2: Preflight checks — command existence and Python version

**Files:**
- Modify: `src/ananta/explorers/launcher.py`
- Modify: `tests/unit/explorers/test_launcher.py`

**Step 1: Write failing tests for command checks**

Add to `tests/unit/explorers/test_launcher.py`:

```python
from unittest.mock import patch

from ananta.explorers.launcher import check_command, check_python_version


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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py::TestCheckCommand -v`
Expected: FAIL — `ImportError: cannot import name 'check_command'`

**Step 3: Write minimal implementation**

Add to `src/ananta/explorers/launcher.py`:

```python
import shutil
import sys


def check_command(cmd: str, install_hint: str) -> str | None:
    """Return an error string if cmd is not on PATH, else None."""
    if shutil.which(cmd) is None:
        return f"  - Install {cmd}: {install_hint}"
    return None


def check_python_version() -> str | None:
    """Return an error string if Python < 3.11, else None."""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        return f"  - Upgrade Python: 3.11+ required, found {major}.{minor}"
    return None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py::TestCheckCommand tests/unit/explorers/test_launcher.py::TestCheckPythonVersion -v`
Expected: all PASS

**Step 5: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add command existence and Python version preflight checks"
```

---

### Task 3: Preflight checks — env vars, Docker daemon, sandbox image

**Files:**
- Modify: `src/ananta/explorers/launcher.py`
- Modify: `tests/unit/explorers/test_launcher.py`

**Step 1: Write failing tests for env var check**

Add to `tests/unit/explorers/test_launcher.py`:

```python
import os

from ananta.explorers.launcher import check_env_var


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
```

**Step 2: Write failing tests for Docker daemon check**

```python
import subprocess

from ananta.explorers.launcher import check_docker_running


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
```

**Step 3: Write failing tests for sandbox image check**

```python
from ananta.explorers.launcher import ensure_sandbox_image


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
```

**Step 4: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py::TestCheckEnvVar tests/unit/explorers/test_launcher.py::TestCheckDockerRunning tests/unit/explorers/test_launcher.py::TestEnsureSandboxImage -v`
Expected: FAIL — `ImportError`

**Step 5: Write minimal implementation**

Add to `src/ananta/explorers/launcher.py`:

```python
import os
import subprocess


def check_env_var(var: str, hint: str) -> str | None:
    """Return an error string if the env var is unset or empty, else None."""
    if not os.environ.get(var):
        return f"  - Set {var}: {hint}"
    return None


def check_docker_running() -> str | None:
    """Return an error string if Docker daemon is not running, else None."""
    if shutil.which("docker") is None:
        return None  # check_command will catch this
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return "  - Start Docker daemon (e.g. open Docker Desktop)"
    return None


def ensure_sandbox_image(project_root: str) -> str | None:
    """Build the sandbox image if missing. Return error string on failure, else None."""
    image = os.environ.get("ANANTA_SANDBOX_IMAGE", "ananta-sandbox")
    if shutil.which("docker") is None:
        return None  # check_command will catch this
    try:
        subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            check=True,
        )
        return None  # Image exists
    except subprocess.CalledProcessError:
        pass  # Image missing, try to build

    print(f"[ananta] Building sandbox image ({image})...")
    try:
        subprocess.run(
            ["docker", "build", "-t", image, f"{project_root}/src/ananta/sandbox/"],
            check=True,
        )
    except subprocess.CalledProcessError:
        return f"  - Failed to build Docker image '{image}'"
    return None
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py::TestCheckEnvVar tests/unit/explorers/test_launcher.py::TestCheckDockerRunning tests/unit/explorers/test_launcher.py::TestEnsureSandboxImage -v`
Expected: all PASS

**Step 7: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add env var, Docker daemon, and sandbox image preflight checks"
```

---

### Task 4: Preflight orchestrator — run_preflight()

**Files:**
- Modify: `src/ananta/explorers/launcher.py`
- Modify: `tests/unit/explorers/test_launcher.py`

**Step 1: Write failing tests**

Add to `tests/unit/explorers/test_launcher.py`:

```python
from ananta.explorers.launcher import run_preflight, LauncherConfig


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

    @patch("ananta.explorers.launcher.check_command")
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    def test_collects_multiple_errors(self, mock_cmd: object, *mocks: object) -> None:
        mock_cmd.side_effect = lambda cmd, hint: f"  - missing {cmd}" if cmd == "node" else None
        errors = run_preflight(self._make_config(), "/project")
        assert len(errors) == 1
        assert "node" in errors[0]

    @patch("ananta.explorers.launcher.ensure_sandbox_image", return_value=None)
    @patch("ananta.explorers.launcher.check_docker_running", return_value=None)
    @patch("ananta.explorers.launcher.check_env_var", return_value=None)
    @patch("ananta.explorers.launcher.check_python_version", return_value=None)
    @patch("ananta.explorers.launcher.check_command", return_value=None)
    def test_git_checked_when_required(
        self, mock_cmd: object, *mocks: object
    ) -> None:
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
    def test_git_not_checked_when_not_required(
        self, mock_cmd: object, *mocks: object
    ) -> None:
        config = self._make_config(requires_git=False)
        run_preflight(config, "/project")
        cmd_names = [call.args[0] for call in mock_cmd.call_args_list]  # type: ignore[attr-defined]
        assert "git" not in cmd_names
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py::TestRunPreflight -v`
Expected: FAIL — `ImportError: cannot import name 'run_preflight'`

**Step 3: Write minimal implementation**

Add to `src/ananta/explorers/launcher.py`:

```python
def run_preflight(config: LauncherConfig, project_root: str) -> list[str]:
    """Run all preflight checks. Return list of error strings (empty = all OK)."""
    errors: list[str] = []

    def collect(result: str | None) -> None:
        if result is not None:
            errors.append(result)

    collect(check_python_version())
    collect(check_command("node", "https://nodejs.org/"))
    collect(check_command("npm", "https://nodejs.org/"))
    collect(check_command("docker", "https://www.docker.com/get-started/"))
    if config.requires_git:
        collect(check_command("git", "https://git-scm.com/"))
    collect(check_env_var("ANANTA_API_KEY", "export ANANTA_API_KEY=<your-key>"))
    collect(check_env_var("ANANTA_MODEL", "export ANANTA_MODEL=<model-name>"))
    collect(check_docker_running())
    collect(ensure_sandbox_image(project_root))

    return errors
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py::TestRunPreflight -v`
Expected: all PASS

**Step 5: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add run_preflight orchestrator collecting all check errors"
```

---

### Task 5: Frontend build logic

**Files:**
- Modify: `src/ananta/explorers/launcher.py`
- Modify: `tests/unit/explorers/test_launcher.py`

**Step 1: Write failing tests**

Add to `tests/unit/explorers/test_launcher.py`:

```python
from pathlib import Path

from ananta.explorers.launcher import build_frontend, LauncherConfig


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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py::TestBuildFrontend -v`
Expected: FAIL — `ImportError: cannot import name 'build_frontend'`

**Step 3: Write minimal implementation**

Add to `src/ananta/explorers/launcher.py`:

```python
from pathlib import Path


def build_frontend(config: LauncherConfig, project_root: str, *, rebuild: bool) -> None:
    """Build the explorer frontend (and shared UI if configured)."""
    frontend_path = Path(config.frontend_dir)
    if not frontend_path.is_absolute():
        frontend_path = Path(project_root) / frontend_path
    dist_path = frontend_path / "dist"

    needs_build = rebuild or not dist_path.is_dir()

    if not needs_build:
        print("[ananta] Frontend already built. Use --rebuild to force.")
        return

    if config.shared_frontend_dir:
        shared_path = Path(config.shared_frontend_dir)
        if not shared_path.is_absolute():
            shared_path = Path(project_root) / shared_path
        print("[ananta] Installing shared UI dependencies...")
        subprocess.run(["npm", "install", "--silent"], cwd=shared_path, check=True)

    print("[ananta] Building frontend...")
    subprocess.run(["npm", "install", "--silent"], cwd=frontend_path, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend_path, check=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py::TestBuildFrontend -v`
Expected: all PASS

**Step 5: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add frontend build logic with shared UI and --rebuild support"
```

---

### Task 6: launch() function — tie it all together

**Files:**
- Modify: `src/ananta/explorers/launcher.py`
- Modify: `tests/unit/explorers/test_launcher.py`

**Step 1: Write failing tests**

Add to `tests/unit/explorers/test_launcher.py`:

```python
from ananta.explorers.launcher import launch, LauncherConfig


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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/explorers/test_launcher.py::TestLaunch -v`
Expected: FAIL — `launch` doesn't exist or wrong signature

**Step 3: Write minimal implementation**

Add to `src/ananta/explorers/launcher.py`:

```python
def launch(
    config: LauncherConfig,
    *,
    argv: list[str] | None = None,
    project_root: str | None = None,
) -> int:
    """Run preflight checks, build frontend, and launch the explorer.

    Returns the process exit code (0 = success).
    """
    if argv is None:
        argv = sys.argv[1:]
    if project_root is None:
        # Resolve from this file: src/ananta/explorers/launcher.py -> project root
        project_root = str(Path(__file__).resolve().parents[3])

    rebuild, passthrough = parse_launcher_args(argv)

    # Preflight
    errors = run_preflight(config, project_root)
    if errors:
        print(f"\033[0;31m[ananta]\033[0m Cannot start {config.app_name}. Fix the following:",
              file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    # Build frontend
    build_frontend(config, project_root, rebuild=rebuild)

    # Launch
    print(f"[ananta] Starting {config.app_name}...")
    result = subprocess.run([config.entry_point, *passthrough])
    return result.returncode
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/explorers/test_launcher.py::TestLaunch -v`
Expected: all PASS

**Step 5: Run all launcher tests**

Run: `pytest tests/unit/explorers/test_launcher.py -v`
Expected: all PASS

**Step 6: Commit**

```
git add src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py
git commit -m "feat: add launch() function tying together preflight, build, and exec"
```

---

### Task 7: Create per-explorer launch.py files

**Files:**
- Create: `arxiv-explorer/launch.py`
- Create: `code-explorer/launch.py`
- Create: `document-explorer/launch.py`

**Step 1: Create arxiv-explorer/launch.py**

```python
#!/usr/bin/env python3
"""Launch the Ananta arXiv Web Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta arXiv Web Explorer",
    entry_point="ananta-web",
    frontend_dir="src/ananta/explorers/arxiv/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
```

**Step 2: Create code-explorer/launch.py**

```python
#!/usr/bin/env python3
"""Launch the Ananta Code Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta Code Explorer",
    entry_point="ananta-code",
    frontend_dir="src/ananta/explorers/code/frontend",
    requires_git=True,
    shared_frontend_dir="src/ananta/explorers/shared_ui/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
```

**Step 3: Create document-explorer/launch.py**

```python
#!/usr/bin/env python3
"""Launch the Ananta Document Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta Document Explorer",
    entry_point="ananta-document-explorer",
    frontend_dir="src/ananta/explorers/document/frontend",
    shared_frontend_dir="src/ananta/explorers/shared_ui/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
```

**Step 4: Verify all three files parse correctly**

Run: `python -c "import ast; [ast.parse(open(f).read()) for f in ['arxiv-explorer/launch.py', 'code-explorer/launch.py', 'document-explorer/launch.py']]" && echo "All OK"`
Expected: `All OK`

**Step 5: Commit**

```
git add arxiv-explorer/launch.py code-explorer/launch.py document-explorer/launch.py
git commit -m "feat: add per-explorer launch.py config files"
```

---

### Task 8: Rewrite bash shims

**Files:**
- Rewrite: `arxiv-explorer/arxiv-explorer.sh`
- Rewrite: `code-explorer/code-explorer.sh`
- Rewrite: `document-explorer/document-explorer.sh`

**Step 1: Rewrite arxiv-explorer/arxiv-explorer.sh**

```bash
#!/usr/bin/env bash
# Launch the Ananta arXiv Web Explorer.
# Usage:
#   ./arxiv-explorer/arxiv-explorer.sh                      # defaults
#   ./arxiv-explorer/arxiv-explorer.sh --model gpt-5-mini   # pass args to ananta-web
#   ./arxiv-explorer/arxiv-explorer.sh --port 8080          # custom port
#   ./arxiv-explorer/arxiv-explorer.sh --open               # open browser on startup
#   ./arxiv-explorer/arxiv-explorer.sh --rebuild            # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PIP_EXTRA="web"
APP_SLUG="ananta-web"

if [ ! -d "$VENV_DIR" ]; then
    echo "[ananta] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

MARKER="$VENV_DIR/.${APP_SLUG}-installed"
if [ ! -f "$MARKER" ] || [ "$PROJECT_ROOT/pyproject.toml" -nt "$MARKER" ]; then
    echo "[ananta] Installing Python dependencies..."
    pip install -q -e "$PROJECT_ROOT[$PIP_EXTRA]"
    touch "$MARKER"
fi

exec python "$SCRIPT_DIR/launch.py" "$@"
```

**Step 2: Rewrite code-explorer/code-explorer.sh**

Same structure, with `PIP_EXTRA="web"` and `APP_SLUG="ananta-code"`.

**Step 3: Rewrite document-explorer/document-explorer.sh**

Same structure, with `PIP_EXTRA="document-explorer"` and `APP_SLUG="ananta-document-explorer"`.

**Step 4: Verify all shims parse**

Run: `bash -n arxiv-explorer/arxiv-explorer.sh && bash -n code-explorer/code-explorer.sh && bash -n document-explorer/document-explorer.sh && echo "All OK"`
Expected: `All OK`

**Step 5: Commit**

```
git add arxiv-explorer/arxiv-explorer.sh code-explorer/code-explorer.sh document-explorer/document-explorer.sh
git commit -m "refactor: rewrite explorer shell scripts as thin venv-bootstrap shims"
```

---

### Task 9: Delete stale files

**Files:**
- Delete: `scripts/common.sh`
- Delete: `examples/arxiv-explorer.sh`

**Step 1: Verify no other files source common.sh**

Run: `grep -r "common.sh" --include="*.sh" . | grep -v ".git/"` — should only show the three old shims (now rewritten) and itself.

**Step 2: Delete the files**

```bash
git rm scripts/common.sh examples/arxiv-explorer.sh
```

**Step 3: Remove scripts/ directory if empty**

Run: `rmdir scripts/ 2>/dev/null || true`

**Step 4: Commit**

```
git commit -m "remove: delete scripts/common.sh and stale examples/arxiv-explorer.sh"
```

---

### Task 10: Update README.md and CHANGELOG.md

**Files:**
- Modify: `README.md:317-335`
- Modify: `CHANGELOG.md:8`

**Step 1: Update README Document Explorer section**

Replace lines 317-335 in `README.md` with:

```markdown
## Document Explorer

A web-based interface for uploading documents, organizing them into topics, and querying them with Ananta. Upload PDFs, Word documents, PowerPoint, Excel, RTF, or plain text files, group them by topic, then ask questions across your collection.

```bash
# Launch the Document Explorer
./document-explorer/document-explorer.sh

# Options
./document-explorer/document-explorer.sh --port 8003 --open --model gpt-4o
```

The explorer provides:
- **Drag-and-drop upload** with automatic text extraction
- **Topic organization** — group related documents and query within a topic
- **Live query streaming** via WebSocket — watch Ananta think in real time
- **Conversation history** per topic for follow-up questions
```

Note: the `> **Note:** This is experimental...` line is also removed.

**Step 2: Update CHANGELOG.md**

Add under `## [Unreleased]`:

```markdown
### Changed

- Explorer launcher scripts rewritten: bash logic moved to testable Python (`src/ananta/explorers/launcher.py`), shell scripts reduced to venv-bootstrap shims

### Removed

- `scripts/common.sh` — replaced by Python launcher module
- `examples/arxiv-explorer.sh` — stale launcher pointing at old paths
```

**Step 3: Commit**

```
git add README.md CHANGELOG.md
git commit -m "docs: update README Document Explorer section and changelog for launcher rewrite"
```

---

### Task 11: Run full test suite and lint

**Step 1: Run ruff**

Run: `ruff check src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py`
Expected: no errors (fix any that appear)

**Step 2: Run ruff format**

Run: `ruff format src/ananta/explorers/launcher.py tests/unit/explorers/test_launcher.py`

**Step 3: Run mypy**

Run: `mypy src/ananta/explorers/launcher.py`
Expected: no errors (fix any that appear)

**Step 4: Run full test suite**

Run: `make all`
Expected: all pass

**Step 5: Commit any fixes**

```
git add -u
git commit -m "chore: lint and format fixes for launcher module"
```
