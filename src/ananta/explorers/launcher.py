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
