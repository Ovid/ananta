"""Shared state and factory for explorer web APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ananta import Ananta
from ananta.config import AnantaConfig
from ananta.experimental.shared.session import WebConversationSession
from ananta.experimental.shared.topics import BaseTopicManager
from ananta.repo.ingester import RepoIngester
from ananta.storage.filesystem import FilesystemStorage


@dataclass
class BaseExplorerState:
    """Shared application state for explorers."""

    ananta: Ananta
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
    data_dir = data_dir or Path.home() / ".ananta" / app_name
    ananta_data = data_dir / "ananta_data"
    topics_dir = data_dir / "topics"
    ananta_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    resolved_extra: dict[str, Path] = {}
    if extra_dirs:
        for key, dirname in extra_dirs.items():
            p = data_dir / dirname
            p.mkdir(parents=True, exist_ok=True)
            resolved_extra[key] = p

    config = AnantaConfig.load(storage_path=str(ananta_data))
    if model:
        config.model = model

    storage = FilesystemStorage(ananta_data)
    repo_ingester = RepoIngester(
        storage_path=config.storage_path,
        allow_local_paths=False,
    )
    ananta = Ananta(config=config, storage=storage, repo_ingester=repo_ingester)
    topic_mgr = topic_mgr_class(topics_dir)
    session = WebConversationSession(data_dir)

    return BaseExplorerState(
        ananta=ananta,
        topic_mgr=topic_mgr,
        session=session,
        model=config.model,
        extra_dirs=resolved_extra,
    )
