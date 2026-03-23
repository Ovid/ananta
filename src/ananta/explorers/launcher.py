"""Shared launcher logic for Ananta explorer applications."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


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
    # Default must match AnantaConfig.sandbox_image in config.py
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
        print(
            f"\033[0;31m[ananta]\033[0m Cannot start {config.app_name}. Fix the following:",
            file=sys.stderr,
        )
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    # Build frontend
    try:
        build_frontend(config, project_root, rebuild=rebuild)
    except subprocess.CalledProcessError:
        print(
            f"\033[0;31m[ananta]\033[0m Frontend build failed for {config.app_name}.",
            file=sys.stderr,
        )
        return 1

    # Launch
    print(f"[ananta] Starting {config.app_name}...")
    result = subprocess.run([config.entry_point, *passthrough])
    return result.returncode


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
