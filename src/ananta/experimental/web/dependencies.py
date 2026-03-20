"""Shared state for the web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.search import ArxivSearcher
from shesha.experimental.arxiv.topics import TopicManager
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class AppState:
    """Shared application state."""

    shesha: Shesha
    topic_mgr: TopicManager
    cache: PaperCache
    searcher: ArxivSearcher
    model: str
    download_tasks: dict[str, dict[str, object]] = field(default_factory=dict)


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> AppState:
    """Initialize all components and return shared state."""
    data_dir = data_dir or Path.home() / ".shesha-arxiv"
    shesha_data = data_dir / "shesha_data"
    cache_dir = data_dir / "paper-cache"
    shesha_data.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model
    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    cache = PaperCache(cache_dir)
    searcher = ArxivSearcher()
    topic_mgr = TopicManager(shesha=shesha, storage=storage)

    return AppState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
        model=config.model,
    )
