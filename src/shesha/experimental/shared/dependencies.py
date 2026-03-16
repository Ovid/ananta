"""Shared state and factory for explorer web APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.shared.session import WebConversationSession
from shesha.experimental.shared.topics import BaseTopicManager
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class BaseExplorerState:
    """Shared application state for explorers."""

    shesha: Shesha
    topic_mgr: BaseTopicManager
    session: WebConversationSession
    model: str
    extra_dirs: dict[str, Path] = field(default_factory=dict)


def get_topic_session(
    state: BaseExplorerState,
    topic_name: str,
) -> WebConversationSession:
    """Return a per-topic session stored in the topic's directory."""
    topic_dir = state.topic_mgr.get_topic_dir(topic_name)
    return WebConversationSession(topic_dir)


def create_app_state(
    app_name: str,
    topic_mgr_class: type[BaseTopicManager],
    data_dir: Path | None = None,
    model: str | None = None,
    extra_dirs: dict[str, str] | None = None,
) -> BaseExplorerState:
    """Initialize all components and return shared state."""
    data_dir = data_dir or Path.home() / ".shesha" / app_name
    shesha_data = data_dir / "shesha_data"
    topics_dir = data_dir / "topics"
    shesha_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    resolved_extra: dict[str, Path] = {}
    if extra_dirs:
        for key, dirname in extra_dirs.items():
            p = data_dir / dirname
            p.mkdir(parents=True, exist_ok=True)
            resolved_extra[key] = p

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model

    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    topic_mgr = topic_mgr_class(topics_dir)
    session = WebConversationSession(data_dir)

    return BaseExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model=config.model,
        extra_dirs=resolved_extra,
    )
