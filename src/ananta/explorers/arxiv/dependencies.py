"""Shared state for the web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ananta import Ananta
from ananta.config import AnantaConfig
from ananta.experimental.arxiv.cache import PaperCache
from ananta.experimental.arxiv.search import ArxivSearcher
from ananta.experimental.arxiv.topics import TopicManager
from ananta.migration import check_legacy_directory
from ananta.repo.ingester import RepoIngester
from ananta.storage.filesystem import FilesystemStorage


@dataclass
class AppState:
    """Shared application state."""

    ananta: Ananta
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
    data_dir = data_dir or Path.home() / ".ananta-arxiv"

    legacy_arxiv = Path.home() / ".shesha-arxiv"
    check_legacy_directory(legacy_arxiv, data_dir, ".shesha-arxiv", ".ananta-arxiv")

    ananta_data = data_dir / "ananta_data"
    cache_dir = data_dir / "paper-cache"
    ananta_data.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    config = AnantaConfig.load(storage_path=str(ananta_data))
    if model:
        config.model = model
    storage = FilesystemStorage(ananta_data)
    repo_ingester = RepoIngester(
        storage_path=str(ananta_data),
        allow_local_paths=False,
    )
    ananta = Ananta(config=config, storage=storage, repo_ingester=repo_ingester)
    cache = PaperCache(cache_dir)
    searcher = ArxivSearcher()
    topic_mgr = TopicManager(ananta=ananta, storage=storage)

    return AppState(
        ananta=ananta,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
        model=config.model,
    )
