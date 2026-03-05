"""Shared state for the document explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.document_explorer.topics import DocumentTopicManager
from shesha.experimental.shared.session import WebConversationSession
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class DocumentExplorerState:
    """Shared application state for the document explorer."""

    shesha: Shesha
    topic_mgr: DocumentTopicManager
    session: WebConversationSession
    model: str
    uploads_dir: Path


def get_topic_session(
    state: DocumentExplorerState,
    topic_name: str,
) -> WebConversationSession:
    """Return a per-topic session stored in the topic's directory."""
    topic_dir = state.topic_mgr.get_topic_dir(topic_name)
    return WebConversationSession(topic_dir)


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> DocumentExplorerState:
    """Initialize all components and return shared state."""
    data_dir = data_dir or Path.home() / ".shesha" / "document-explorer"
    shesha_data = data_dir / "shesha_data"
    topics_dir = data_dir / "topics"
    uploads_dir = data_dir / "uploads"
    shesha_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model

    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    topic_mgr = DocumentTopicManager(topics_dir)
    session = WebConversationSession(data_dir)

    return DocumentExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model=config.model,
        uploads_dir=uploads_dir,
    )
