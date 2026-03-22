"""Shared launcher logic for Ananta explorer applications."""

from __future__ import annotations

import shutil
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
