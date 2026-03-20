"""Shared state for the document explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha.experimental.document_explorer.topics import DocumentTopicManager
from shesha.experimental.shared.dependencies import (
    BaseExplorerState,
    get_topic_session,
)
from shesha.experimental.shared.dependencies import (
    create_app_state as _create_app_state,
)


@dataclass
class DocumentExplorerState(BaseExplorerState):
    """Application state for the document explorer."""

    @property
    def uploads_dir(self) -> Path:
        return self.extra_dirs["uploads"]


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> DocumentExplorerState:
    """Initialize all components and return document explorer state."""
    base = _create_app_state(
        app_name="document-explorer",
        topic_mgr_class=DocumentTopicManager,
        data_dir=data_dir,
        model=model,
        extra_dirs={"uploads": "uploads"},
    )
    # Narrow the type: BaseExplorerState -> DocumentExplorerState
    return DocumentExplorerState(
        shesha=base.shesha,
        topic_mgr=base.topic_mgr,
        session=base.session,
        model=base.model,
        extra_dirs=base.extra_dirs,
    )


__all__ = [
    "DocumentExplorerState",
    "create_app_state",
    "get_topic_session",
]
