"""Tests for topic manager."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from ananta.storage.filesystem import FilesystemStorage


def _make_ananta_and_storage(tmp_path: Path) -> tuple[MagicMock, FilesystemStorage]:
    """Create a real FilesystemStorage with a mock Ananta that delegates to it."""
    # Late import inside test helper to avoid top-level dependency on ananta internals
    from ananta.storage.filesystem import FilesystemStorage

    storage_path = tmp_path / "ananta_data"
    storage = FilesystemStorage(storage_path)

    ananta = MagicMock()
    ananta.storage = storage
    ananta.list_projects.side_effect = lambda: storage.list_projects()
    ananta.delete_project.side_effect = lambda pid, cleanup_repo=True: storage.delete_project(pid)
    return ananta, storage


class TestTopicManager:
    """Tests for TopicManager."""

    def test_create_topic(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("quantum-error-correction")
        assert "quantum-error-correction" in project_id
        assert storage.project_exists(project_id)

    def test_create_topic_includes_date(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("test-topic")
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        assert project_id.startswith(today)

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        assert mgr.list_topics() == []

    def test_list_topics_returns_topic_info(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        mgr.create("topic-a")
        topics = mgr.list_topics()
        assert len(topics) == 1
        assert topics[0].name == "topic-a"
        assert topics[0].paper_count == 0
        assert topics[0].size_bytes >= 0

    def test_delete_topic(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("to-delete")
        mgr.delete("to-delete")
        assert not storage.project_exists(project_id)

    def test_resolve_topic_name(self, tmp_path: Path) -> None:
        """Resolve a slug name to a full project ID."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("my-topic")
        resolved = mgr.resolve("my-topic")
        assert resolved == project_id

    def test_resolve_returns_none_for_unknown(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        assert mgr.resolve("nonexistent") is None

    def test_get_topic_info_with_size(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager
        from ananta.models import ParsedDocument

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("sized-topic")
        # Store a document to add some size
        doc = ParsedDocument(
            name="test.txt",
            content="Hello world " * 1000,
            format="text",
            metadata={},
            char_count=12000,
        )
        storage.store_document(project_id, doc)
        info = mgr.get_topic_info("sized-topic")
        assert info is not None
        assert info.paper_count == 1
        assert info.size_bytes > 0

    def test_get_topic_info_by_project_id(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("by-id-test")
        info = mgr.get_topic_info_by_project_id(project_id)
        assert info is not None
        assert info.name == "by-id-test"

    def test_get_topic_info_by_project_id_returns_none(self, tmp_path: Path) -> None:
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        assert mgr.get_topic_info_by_project_id("nonexistent") is None

    def test_create_existing_topic_is_idempotent(self, tmp_path: Path) -> None:
        """Creating a topic that already exists returns its project ID."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id_1 = mgr.create("existing-topic")
        project_id_2 = mgr.create("existing-topic")
        assert project_id_1 == project_id_2
        assert storage.project_exists(project_id_1)

    def test_create_writes_metadata_when_project_exists_without_it(self, tmp_path: Path) -> None:
        """If project exists but _topic.json is missing, create() writes it.

        Regression: old buggy code created the project directory but wrote
        _topic.json to the wrong path. On re-create, ProjectExistsError was
        caught and create() returned without writing metadata.
        """
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)

        # Simulate the stale state: project exists with today's date, no _topic.json
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        stale_id = f"{today}-orphan"
        storage.create_project(stale_id)
        meta_path = storage._project_path(stale_id) / "_topic.json"
        assert not meta_path.exists()

        # create() should write _topic.json even though project already exists
        project_id = mgr.create("orphan")
        assert project_id == stale_id

        # The topic must now be discoverable
        topics = mgr.list_topics()
        topic_names = [t.name for t in topics]
        assert "orphan" in topic_names

    def test_topic_metadata_stored_in_storage_directory(self, tmp_path: Path) -> None:
        """_topic.json must be written inside FilesystemStorage's project dir.

        Regression: TopicManager used data_dir/projects/ but storage uses
        ananta_data/projects/ — the metadata was written to the wrong path.
        """
        from ananta.explorers.arxiv.papers.topics import TopicManager

        # Mirror production layout: data_dir != storage root
        data_dir = tmp_path / "app-data"
        ananta_data = data_dir / "ananta_data"
        ananta_data.mkdir(parents=True)

        from ananta.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(ananta_data)
        ananta = MagicMock()
        ananta.storage = storage

        mgr = TopicManager(ananta, storage)
        mgr.create("regression-test")

        # Metadata must be readable (lives in storage dir, not data_dir)
        topics = mgr.list_topics()
        assert len(topics) == 1
        assert topics[0].name == "regression-test"

    def test_slugify(self, tmp_path: Path) -> None:
        """Topic names are slugified (lowercase, hyphens, no special chars)."""
        from ananta.explorers.arxiv.papers.topics import slugify

        assert slugify("Quantum Error Correction") == "quantum-error-correction"
        assert slugify("cs.AI + language models!") == "cs-ai-language-models"
        assert slugify("  spaces  everywhere  ") == "spaces-everywhere"


class TestTopicRename:
    """Tests for TopicManager.rename()."""

    def test_rename_updates_topic_meta(self, tmp_path: Path) -> None:
        """Renaming a topic updates the name field in _topic.json."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("old-name")

        mgr.rename("old-name", "new-name")

        meta_path = storage.projects_dir / project_id / "_topic.json"
        meta = json.loads(meta_path.read_text())
        assert meta["name"] == "new-name"

    def test_rename_not_found_raises(self, tmp_path: Path) -> None:
        """Renaming a nonexistent topic raises ValueError."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)

        with pytest.raises(ValueError, match="Topic not found"):
            mgr.rename("nonexistent", "new")


class TestDocOrder:
    """Tests for TopicManager.get_doc_order / set_doc_order."""

    def test_get_doc_order_returns_none_when_unset(self, tmp_path: Path) -> None:
        """When no doc_order has been stored, get_doc_order returns None."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("no-order")
        assert mgr.get_doc_order(project_id) is None

    def test_set_and_get_doc_order(self, tmp_path: Path) -> None:
        """set_doc_order stores order, get_doc_order retrieves it."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("ordered")
        mgr.set_doc_order(project_id, ["paper-c", "paper-a", "paper-b"])
        assert mgr.get_doc_order(project_id) == ["paper-c", "paper-a", "paper-b"]

    def test_set_doc_order_preserves_existing_meta(self, tmp_path: Path) -> None:
        """set_doc_order does not clobber other fields in _topic.json."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("preserve-meta")

        mgr.set_doc_order(project_id, ["a", "b"])

        meta_path = storage.get_project_dir(project_id) / "_topic.json"
        meta = json.loads(meta_path.read_text())
        assert meta["name"] == "preserve-meta"
        assert "created" in meta
        assert meta["doc_order"] == ["a", "b"]

    def test_set_doc_order_overwrites_previous(self, tmp_path: Path) -> None:
        """Calling set_doc_order again replaces the previous order."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        project_id = mgr.create("overwrite")

        mgr.set_doc_order(project_id, ["x", "y"])
        mgr.set_doc_order(project_id, ["y", "x"])
        assert mgr.get_doc_order(project_id) == ["y", "x"]

    def test_get_doc_order_returns_none_for_missing_project(self, tmp_path: Path) -> None:
        """get_doc_order returns None when project has no _topic.json."""
        from ananta.explorers.arxiv.papers.topics import TopicManager

        ananta, storage = _make_ananta_and_storage(tmp_path)
        mgr = TopicManager(ananta, storage)
        assert mgr.get_doc_order("nonexistent-project") is None
