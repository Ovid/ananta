"""Shared state for the code explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.dependencies import (
    BaseExplorerState,
    create_app_state as _create_app_state,
    get_topic_session,
)


@dataclass
class CodeExplorerState(BaseExplorerState):
    """Application state for the code explorer."""

    pass


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> CodeExplorerState:
    """Initialize all components and return code explorer state."""
    base = _create_app_state(
        app_name="code-explorer",
        topic_mgr_class=CodeExplorerTopicManager,
        data_dir=data_dir,
        model=model,
    )
    return CodeExplorerState(
        shesha=base.shesha,
        topic_mgr=base.topic_mgr,
        session=base.session,
        model=base.model,
        extra_dirs=base.extra_dirs,
    )


__all__ = [
    "CodeExplorerState",
    "create_app_state",
    "get_topic_session",
]
