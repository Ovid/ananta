"""Shared launcher logic for Ananta explorer applications."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
