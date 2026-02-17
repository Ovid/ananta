"""Shared state for the code explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.session import WebConversationSession
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class CodeExplorerState:
    """Shared application state for the code explorer."""

    shesha: Shesha
    topic_mgr: CodeExplorerTopicManager
    session: WebConversationSession
    model: str


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> CodeExplorerState:
    """Initialize all components and return shared state."""
    data_dir = data_dir or Path.home() / ".shesha" / "code-explorer"
    shesha_data = data_dir / "shesha_data"
    topics_dir = data_dir / "topics"
    shesha_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model

    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    topic_mgr = CodeExplorerTopicManager(topics_dir)
    session = WebConversationSession(data_dir)

    return CodeExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model=config.model,
    )
