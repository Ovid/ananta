# Refactor Explorers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate ~1200-1500 lines of duplication across document_explorer and code_explorer by extracting shared base classes for topics, dependencies, API routes, and WebSocket handlers.

**Architecture:** A shared `BaseTopicManager` replaces both topic managers with generic `add_item`/`list_items` methods. Shared factories handle dependencies, API routes, and WebSocket query execution. Each explorer becomes a thin wrapper providing only domain-specific behavior.

**Tech Stack:** Python, FastAPI, pytest, asyncio

---

### Task 1: BaseTopicManager — Test the core

**Files:**
- Create: `src/shesha/experimental/shared/topics.py`
- Create: `tests/unit/experimental/shared/test_topics.py`

**Step 1: Write failing tests for BaseTopicManager**

Create `tests/unit/experimental/shared/test_topics.py`:

```python
"""Tests for BaseTopicManager."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from shesha.experimental.shared.topics import BaseTopicManager, _slugify

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class TestSlugify:
    """_slugify output must match _SAFE_ID_RE so generated IDs are API-valid."""

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("hello world", "hello-world"),
            ("My Report", "my-report"),
            ("file_name", "file-name"),
            ("a--b", "a-b"),
        ],
    )
    def test_basic_slugs(self, input_text: str, expected: str) -> None:
        assert _slugify(input_text) == expected

    @pytest.mark.parametrize(
        "input_text",
        ["résumé", "über", "café_report", "naïve-analysis"],
    )
    def test_unicode_slugs_match_safe_id(self, input_text: str) -> None:
        slug = _slugify(input_text)
        assert slug, f"_slugify({input_text!r}) returned empty string"
        assert _SAFE_ID_RE.match(slug), (
            f"_slugify({input_text!r}) = {slug!r} does not match _SAFE_ID_RE"
        )

    def test_pure_non_latin_returns_empty(self) -> None:
        assert _slugify("日本語") == ""

    def test_mixed_ascii_and_cjk_keeps_ascii_part(self) -> None:
        slug = _slugify("report-日本語-2024")
        assert _SAFE_ID_RE.match(slug), f"{slug!r} does not match _SAFE_ID_RE"
        assert "report" in slug


class TestCorruptMetaHandling:
    """Corrupt or partially-written topic.json should not crash callers."""

    def test_missing_name_key_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"items": ["a"]}')
        assert mgr.list_topics() == []

    def test_missing_items_key_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": "Reports"}')
        assert mgr.list_topics() == []

    def test_wrong_type_name_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": 42, "items": []}')
        assert mgr.list_topics() == []

    def test_wrong_type_items_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": "Reports", "items": "not-a-list"}')
        assert mgr.list_topics() == []

    def test_valid_topics_unaffected_by_corrupt_sibling(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Good")
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()
        (broken_dir / "topic.json").write_text("{bad json")
        assert mgr.list_topics() == ["Good"]


class TestCreateAndListTopics:
    def test_create_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        assert "Reports" in mgr.list_topics()

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        assert mgr.list_topics() == []

    def test_list_topics_multiple(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Contracts")
        mgr.create("Research")
        assert sorted(mgr.list_topics()) == ["Contracts", "Reports", "Research"]

    def test_topic_json_uses_items_key(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("My Docs")
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        meta = json.loads((dirs[0] / "topic.json").read_text())
        assert meta["name"] == "My Docs"
        assert meta["items"] == []

    def test_create_duplicate_is_idempotent(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Reports")
        assert mgr.list_topics().count("Reports") == 1

    @pytest.mark.parametrize("name", ["!!!", "   ", "---", ""])
    def test_create_rejects_empty_slug(self, tmp_path: Path, name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="[Ee]mpty"):
            mgr.create(name)

    @pytest.mark.parametrize("name", ["foo/bar", "a\\b", "x/y/z"])
    def test_create_rejects_path_separators(self, tmp_path: Path, name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="path separator"):
            mgr.create(name)

    def test_create_slug_collision_different_name_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Research")
        with pytest.raises(ValueError, match="different display name"):
            mgr.create("research")

    def test_create_recovers_corrupt_topic_json(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Research")
        topic_dir = mgr.get_topic_dir("Research")
        (topic_dir / "topic.json").write_text("not valid json")
        mgr.create("Research")
        assert "Research" in mgr.list_topics()


class TestAddAndListItems:
    def test_add_item_to_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "quarterly-report-a3f2")
        assert mgr.list_items("Reports") == ["quarterly-report-a3f2"]

    def test_add_multiple_items(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-2")
        assert sorted(mgr.list_items("Reports")) == ["item-1", "item-2"]

    def test_list_items_empty_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.list_items("Empty") == []

    def test_add_duplicate_item_is_idempotent(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-1")
        assert mgr.list_items("Reports") == ["item-1"]

    def test_add_item_to_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.add_item("Nonexistent", "item-1")


class TestRemoveItem:
    def test_remove_item_from_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-2")
        mgr.remove_item("Reports", "item-1")
        assert mgr.list_items("Reports") == ["item-2"]

    def test_remove_nonexistent_item_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        with pytest.raises(ValueError, match="Item not found"):
            mgr.remove_item("Reports", "nonexistent")


class TestSameItemMultipleTopics:
    def test_same_item_in_multiple_topics(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Research")
        mgr.add_item("Reports", "shared-item")
        mgr.add_item("Research", "shared-item")
        assert "shared-item" in mgr.list_items("Reports")
        assert "shared-item" in mgr.list_items("Research")


class TestListAllItems:
    def test_list_all_items(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "item-1")
        mgr.add_item("A", "item-2")
        mgr.add_item("B", "item-2")
        mgr.add_item("B", "item-3")
        assert sorted(mgr.list_all_items()) == ["item-1", "item-2", "item-3"]

    def test_list_all_items_no_duplicates(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        assert mgr.list_all_items() == ["shared"]


class TestUncategorized:
    def test_list_uncategorized(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.add_item("A", "item-1")
        uncategorized = mgr.list_uncategorized(["item-1", "item-2", "item-3"])
        assert sorted(uncategorized) == ["item-2", "item-3"]


class TestDeleteTopic:
    def test_delete_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("ToDelete")
        mgr.delete("ToDelete")
        assert mgr.list_topics() == []


class TestFindTopicsForItem:
    def test_find_topics_for_item(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        assert sorted(mgr.find_topics_for_item("shared")) == ["A", "B"]


class TestRemoveItemFromAll:
    def test_remove_item_from_all(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        mgr.add_item("B", "other")
        mgr.remove_item_from_all("shared")
        assert mgr.list_items("A") == []
        assert mgr.list_items("B") == ["other"]


class TestGetTopicDir:
    def test_returns_topic_directory(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        topic_dir = mgr.get_topic_dir("Reports")
        assert topic_dir.is_dir()
        meta = json.loads((topic_dir / "topic.json").read_text())
        assert meta["name"] == "Reports"

    def test_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.get_topic_dir("Nonexistent")


class TestRenameTopic:
    def test_rename_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Old")
        mgr.add_item("Old", "item-1")
        mgr.rename("Old", "New")
        assert "New" in mgr.list_topics()
        assert "Old" not in mgr.list_topics()
        assert mgr.list_items("New") == ["item-1"]

    def test_rename_to_existing_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.create("Beta")
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("Alpha", "Beta")

    @pytest.mark.parametrize("new_name", ["foo/bar", "a\\b"])
    def test_rename_rejects_path_separators(self, tmp_path: Path, new_name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Safe")
        with pytest.raises(ValueError, match="path separator"):
            mgr.rename("Safe", new_name)
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_topics.py -v`
Expected: FAIL — `ImportError: cannot import name 'BaseTopicManager' from 'shesha.experimental.shared.topics'`

**Step 3: Write BaseTopicManager implementation**

Create `src/shesha/experimental/shared/topics.py`:

```python
"""Shared topic management base class.

Topics are lightweight reference containers that hold project_id strings
pointing to items (documents, repos, etc.). An item can appear in zero or
more topics. Deleting a topic removes the references but not the items.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import unicodedata
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

TOPIC_META_FILE = "topic.json"


class _TopicMeta(TypedDict):
    """Schema for topic.json files."""

    name: str
    items: list[str]


def _slugify(text: str) -> str:
    """Convert text to an ASCII-safe slug matching ``[a-zA-Z0-9._-]``."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class BaseTopicManager:
    """Manages topics as lightweight reference containers for items.

    Each topic is a directory inside *topics_dir* containing a ``topic.json``
    file with the structure::

        {"name": "Reports", "items": ["project-id-1", "project-id-2"]}

    The directory name is a slugified version of the display name.
    """

    def __init__(self, topics_dir: Path) -> None:
        self._topics_dir = topics_dir
        self._topics_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Topic CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_name(name: str) -> None:
        """Reject names that contain path separators."""
        if "/" in name or "\\" in name:
            msg = f"Topic name must not contain a path separator: {name!r}"
            raise ValueError(msg)

    def create(self, name: str) -> None:
        """Create a new topic.  Idempotent -- no error if it already exists."""
        self._validate_name(name)
        slug = _slugify(name)
        if not slug:
            msg = f"Topic name produces an empty slug: {name!r}"
            raise ValueError(msg)
        topic_dir = self._topics_dir / slug
        meta_path = topic_dir / TOPIC_META_FILE

        if meta_path.exists():
            existing = self._read_meta(topic_dir)
            if existing is None:
                logger.warning("Repairing corrupt topic.json in %s", topic_dir)
            elif existing["name"] != name:
                msg = (
                    f"A topic with a different display name already uses "
                    f"slug '{slug}': existing {existing['name']!r} vs "
                    f"requested {name!r}"
                )
                raise ValueError(msg)
            else:
                return  # already exists with same name

        topic_dir.mkdir(parents=True, exist_ok=True)
        meta: _TopicMeta = {"name": name, "items": []}
        meta_path.write_text(json.dumps(meta, indent=2))

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a topic's display name (directory stays the same)."""
        self._validate_name(new_name)
        meta, meta_path = self._resolve(old_name)
        if new_name != old_name:
            existing_names: set[str] = set()
            for d in self._iter_topic_dirs():
                m = self._read_meta(d)
                if m is not None and m["name"] != old_name:
                    existing_names.add(m["name"])
            if new_name in existing_names:
                msg = f"Topic '{new_name}' already exists"
                raise ValueError(msg)
        meta["name"] = new_name
        meta_path.write_text(json.dumps(meta, indent=2))

    def delete(self, name: str) -> None:
        """Delete a topic and its directory.  Items are not affected."""
        _meta, meta_path = self._resolve(name)
        shutil.rmtree(meta_path.parent)

    def list_topics(self) -> list[str]:
        """Return display names of all topics, sorted alphabetically."""
        seen: set[str] = set()
        names: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None and meta["name"] not in seen:
                seen.add(meta["name"])
                names.append(meta["name"])
        return sorted(names)

    # ------------------------------------------------------------------
    # Item references
    # ------------------------------------------------------------------

    def add_item(self, topic: str, project_id: str) -> None:
        """Add an item reference to a topic.  Idempotent."""
        meta, meta_path = self._resolve(topic)
        items = meta["items"]
        if project_id not in items:
            items.append(project_id)
            meta_path.write_text(json.dumps(meta, indent=2))

    def remove_item(self, topic: str, project_id: str) -> None:
        """Remove an item reference from a topic."""
        meta, meta_path = self._resolve(topic)
        items = meta["items"]
        if project_id not in items:
            msg = f"Item not found in topic '{topic}': {project_id}"
            raise ValueError(msg)
        items.remove(project_id)
        meta_path.write_text(json.dumps(meta, indent=2))

    def list_items(self, topic: str) -> list[str]:
        """Return project_ids referenced by a topic."""
        meta, _meta_path = self._resolve(topic)
        return list(meta["items"])

    def list_all_items(self) -> list[str]:
        """Return unique project_ids across all topics."""
        seen: set[str] = set()
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            for item in meta["items"]:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
        return result

    def list_uncategorized(self, all_project_ids: list[str]) -> list[str]:
        """Return project_ids from *all_project_ids* not in any topic."""
        categorized = set(self.list_all_items())
        return [pid for pid in all_project_ids if pid not in categorized]

    def find_topics_for_item(self, project_id: str) -> list[str]:
        """Return display names of all topics that contain *project_id*."""
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None and project_id in meta["items"]:
                result.append(meta["name"])
        return sorted(result)

    def remove_item_from_all(self, project_id: str) -> None:
        """Remove *project_id* from every topic that contains it."""
        for topic_dir in self._iter_topic_dirs():
            meta_path = topic_dir / TOPIC_META_FILE
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            items = meta["items"]
            if project_id in items:
                items.remove(project_id)
                meta_path.write_text(json.dumps(meta, indent=2))

    def get_topic_dir(self, name: str) -> Path:
        """Return the directory for the topic with *name*.

        Raises ``ValueError`` if the topic does not exist.
        """
        _meta, meta_path = self._resolve(name)
        return meta_path.parent

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, name: str) -> tuple[_TopicMeta, Path]:
        """Find a topic by display name and return (meta_dict, meta_path)."""
        for topic_dir in self._iter_topic_dirs():
            meta_path = topic_dir / TOPIC_META_FILE
            meta = self._read_meta(topic_dir)
            if meta is not None and meta["name"] == name:
                return meta, meta_path
        msg = f"Topic not found: {name}"
        raise ValueError(msg)

    def _iter_topic_dirs(self) -> list[Path]:
        """Return subdirectories of topics_dir that contain topic.json."""
        if not self._topics_dir.exists():
            return []
        return sorted(
            d for d in self._topics_dir.iterdir() if d.is_dir() and (d / TOPIC_META_FILE).exists()
        )

    @staticmethod
    def _read_meta(topic_dir: Path) -> _TopicMeta | None:
        """Read topic.json from a directory, or None if missing/corrupt."""
        meta_path = topic_dir / TOPIC_META_FILE
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("name"), str)
            or not isinstance(data.get("items"), list)
        ):
            return None
        return data  # type: ignore[return-value]
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_topics.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/topics.py tests/unit/experimental/shared/test_topics.py
git commit -m "feat: add BaseTopicManager with generic item methods"
```

---

### Task 2: Rewrite subclasses as thin wrappers

**Files:**
- Modify: `src/shesha/experimental/document_explorer/topics.py`
- Modify: `src/shesha/experimental/code_explorer/topics.py`

**Step 1: Rewrite DocumentTopicManager**

Replace `src/shesha/experimental/document_explorer/topics.py` with:

```python
"""Topic management for the document explorer.

Thin subclass of ``BaseTopicManager`` — all logic lives in the base class.
Kept as a separate class so type annotations in ``DocumentExplorerState``
remain specific to this explorer.
"""

from __future__ import annotations

from shesha.experimental.shared.topics import BaseTopicManager, _slugify

__all__ = ["DocumentTopicManager", "_slugify"]


class DocumentTopicManager(BaseTopicManager):
    pass
```

**Step 2: Rewrite CodeExplorerTopicManager**

Replace `src/shesha/experimental/code_explorer/topics.py` with:

```python
"""Topic management for the code explorer.

Thin subclass of ``BaseTopicManager`` — all logic lives in the base class.
Kept as a separate class so type annotations in ``CodeExplorerState``
remain specific to this explorer.
"""

from __future__ import annotations

from shesha.experimental.shared.topics import BaseTopicManager, _slugify

__all__ = ["CodeExplorerTopicManager", "_slugify"]


class CodeExplorerTopicManager(BaseTopicManager):
    pass
```

**Step 3: Run all existing explorer tests**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/document_explorer/test_topics.py tests/unit/experimental/code_explorer/test_topics.py -v`
Expected: FAILURES — tests reference old methods (`add_doc`, `list_docs`, etc.) and old on-disk key (`"docs"`, `"repos"`)

**Step 4: Update document explorer topic tests**

Modify `tests/unit/experimental/document_explorer/test_topics.py`:
- Change all `add_doc` → `add_item`, `remove_doc` → `remove_item`, `list_docs` → `list_items`
- Change `list_all_docs` → `list_all_items`, `list_uncategorized_docs` → `list_uncategorized`
- Change `find_topics_for_doc` → `find_topics_for_item`, `remove_doc_from_all` → `remove_item_from_all`
- Change `"docs"` → `"items"` in JSON assertions
- Change error message assertions: `"Doc not found"` → `"Item not found"`
- Keep `TestSlugify` unchanged (still imported from `document_explorer.topics`)

**Step 5: Update code explorer topic tests**

Same changes for `tests/unit/experimental/code_explorer/test_topics.py`:
- Change all `add_repo` → `add_item`, `remove_repo` → `remove_item`, `list_repos` → `list_items`
- Change `list_all_repos` → `list_all_items`, `list_uncategorized_repos` → `list_uncategorized`
- Change `find_topics_for_repo` → `find_topics_for_item`, `remove_repo_from_all` → `remove_item_from_all`
- Change `"repos"` → `"items"` in JSON assertions
- Change error message assertions: `"Repo not found"` → `"Item not found"`

**Step 6: Run all explorer topic tests**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/document_explorer/test_topics.py tests/unit/experimental/code_explorer/test_topics.py tests/unit/experimental/shared/test_topics.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/shesha/experimental/document_explorer/topics.py src/shesha/experimental/code_explorer/topics.py tests/unit/experimental/document_explorer/test_topics.py tests/unit/experimental/code_explorer/test_topics.py
git commit -m "refactor: rewrite explorer topic managers as thin BaseTopicManager subclasses"
```

---

### Task 3: Shared dependencies

**Files:**
- Create: `src/shesha/experimental/shared/dependencies.py`
- Create: `tests/unit/experimental/shared/test_dependencies.py`
- Modify: `src/shesha/experimental/document_explorer/dependencies.py`
- Modify: `src/shesha/experimental/code_explorer/dependencies.py`

**Step 1: Write failing tests for shared dependencies**

Create `tests/unit/experimental/shared/test_dependencies.py`:

```python
"""Tests for shared explorer dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.experimental.shared.dependencies import (
    BaseExplorerState,
    create_app_state,
    get_topic_session,
)
from shesha.experimental.shared.session import WebConversationSession
from shesha.experimental.shared.topics import BaseTopicManager


class TestBaseExplorerState:
    def test_has_shesha_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "shesha")

    def test_has_topic_mgr_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "topic_mgr")

    def test_has_session_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="test-model",
        )
        assert hasattr(state, "session")

    def test_has_model_attribute(self) -> None:
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=MagicMock(),
            session=MagicMock(),
            model="gpt-5",
        )
        assert state.model == "gpt-5"


class TestCreateAppState:
    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_returns_base_explorer_state(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state, BaseExplorerState)

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_shesha_data_dir(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert (tmp_path / "shesha_data").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_topics_dir(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert (tmp_path / "topics").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_creates_extra_dirs(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
            extra_dirs={"uploads": "uploads"},
        )
        assert (tmp_path / "uploads").is_dir()
        assert state.extra_dirs["uploads"] == tmp_path / "uploads"

    @patch("shesha.experimental.shared.dependencies.Shesha")
    @patch("shesha.experimental.shared.dependencies.Path.home")
    def test_default_data_dir(
        self, mock_home: MagicMock, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_home.return_value = tmp_path
        state = create_app_state(
            app_name="my-explorer",
            topic_mgr_class=BaseTopicManager,
        )
        expected = tmp_path / ".shesha" / "my-explorer"
        assert (expected / "shesha_data").is_dir()
        assert (expected / "topics").is_dir()

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_model_override(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
            model="custom-model",
        )
        assert state.model == "custom-model"

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_state_has_topic_mgr(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state.topic_mgr, BaseTopicManager)

    @patch("shesha.experimental.shared.dependencies.Shesha")
    def test_state_has_session(
        self, mock_shesha_cls: MagicMock, tmp_path: Path
    ) -> None:
        state = create_app_state(
            app_name="test-explorer",
            topic_mgr_class=BaseTopicManager,
            data_dir=tmp_path,
        )
        assert isinstance(state.session, WebConversationSession)


class TestGetTopicSession:
    def test_returns_session_for_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path / "topics")
        mgr.create("Research")
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=mgr,
            session=MagicMock(),
            model="test",
        )
        session = get_topic_session(state, "Research")
        assert isinstance(session, WebConversationSession)

    def test_raises_for_nonexistent_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path / "topics")
        state = BaseExplorerState(
            shesha=MagicMock(),
            topic_mgr=mgr,
            session=MagicMock(),
            model="test",
        )
        with pytest.raises(ValueError, match="Topic not found"):
            get_topic_session(state, "Nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_dependencies.py -v`
Expected: FAIL — `ImportError`

**Step 3: Write shared dependencies implementation**

Create `src/shesha/experimental/shared/dependencies.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_dependencies.py -v`
Expected: All PASS

**Step 5: Rewrite explorer dependencies as thin wrappers**

Replace `src/shesha/experimental/document_explorer/dependencies.py`:

```python
"""Shared state for the document explorer web API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shesha.experimental.document_explorer.topics import DocumentTopicManager
from shesha.experimental.shared.dependencies import (
    BaseExplorerState,
    create_app_state as _create_app_state,
    get_topic_session,
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
```

Replace `src/shesha/experimental/code_explorer/dependencies.py`:

```python
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
```

**Step 6: Update document_explorer dependency tests**

Modify `tests/unit/experimental/document_explorer/test_dependencies.py`:
- Change `state.uploads_dir` → `state.uploads_dir` (this is now a property, should still work)
- Change `@patch` targets from `shesha.experimental.document_explorer.dependencies.Shesha` to `shesha.experimental.shared.dependencies.Shesha` (since `Shesha` is now imported in the shared module)
- Change `@patch` for `Path.home` similarly: `shesha.experimental.shared.dependencies.Path.home`

**Step 7: Update code_explorer dependency tests**

Same pattern — change `@patch` targets from `shesha.experimental.code_explorer.dependencies.*` to `shesha.experimental.shared.dependencies.*`.

**Step 8: Run all dependency tests**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_dependencies.py tests/unit/experimental/document_explorer/test_dependencies.py tests/unit/experimental/code_explorer/test_dependencies.py -v`
Expected: All PASS

**Step 9: Commit**

```bash
git add src/shesha/experimental/shared/dependencies.py tests/unit/experimental/shared/test_dependencies.py src/shesha/experimental/document_explorer/dependencies.py src/shesha/experimental/code_explorer/dependencies.py tests/unit/experimental/document_explorer/test_dependencies.py tests/unit/experimental/code_explorer/test_dependencies.py
git commit -m "refactor: extract shared explorer dependencies with factory function"
```

---

### Task 4: Shared API topic/item routes

**Files:**
- Modify: `src/shesha/experimental/shared/routes.py`
- Modify: `src/shesha/experimental/document_explorer/api.py`
- Modify: `src/shesha/experimental/code_explorer/api.py`

**Step 1: Write failing test for shared topic error mapper**

Add to `tests/unit/experimental/shared/test_routes.py` (it already exists — read it first, then append):

```python
class TestTopicErrorToStatus:
    def test_already_exists_returns_409(self) -> None:
        from shesha.experimental.shared.routes import _topic_error_to_status
        assert _topic_error_to_status(ValueError("Topic 'X' already exists")) == 409

    def test_not_found_returns_404(self) -> None:
        from shesha.experimental.shared.routes import _topic_error_to_status
        assert _topic_error_to_status(ValueError("Topic not found: X")) == 404

    def test_other_error_returns_422(self) -> None:
        from shesha.experimental.shared.routes import _topic_error_to_status
        assert _topic_error_to_status(ValueError("empty slug")) == 422
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_routes.py::TestTopicErrorToStatus -v`
Expected: FAIL — `ImportError: cannot import name '_topic_error_to_status'`

**Step 3: Add `_topic_error_to_status` to `routes.py`**

Add to `src/shesha/experimental/shared/routes.py` (after the existing imports, before `create_shared_router`):

```python
def _topic_error_to_status(e: ValueError) -> int:
    """Map a topic manager ValueError to an HTTP status code."""
    msg = str(e)
    if "already exists" in msg:
        return 409
    if "not found" in msg.lower():
        return 404
    return 422
```

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_routes.py::TestTopicErrorToStatus -v`
Expected: PASS

**Step 5: Write failing test for item route factory**

Add to `tests/unit/experimental/shared/test_routes.py`:

```python
class TestCreateItemRouter:
    """Tests for the shared topic CRUD + item reference route factory."""

    @pytest.fixture
    def topic_mgr(self, tmp_path: Path) -> BaseTopicManager:
        from shesha.experimental.shared.topics import BaseTopicManager
        return BaseTopicManager(tmp_path / "topics")

    @pytest.fixture
    def client(self, topic_mgr: BaseTopicManager) -> TestClient:
        from shesha.experimental.shared.routes import create_item_router
        from fastapi import FastAPI
        app = FastAPI()
        router = create_item_router(topic_mgr)
        app.include_router(router)
        return TestClient(app)

    def test_create_topic(self, client: TestClient) -> None:
        resp = client.post("/api/topics", json={"name": "Research"})
        assert resp.status_code == 201

    def test_create_topic_invalid_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/topics", json={"name": "!!!"})
        assert resp.status_code == 422

    def test_list_topics(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Alpha")
        topic_mgr.create("Beta")
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert sorted(names) == ["Alpha", "Beta"]

    def test_rename_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Old")
        resp = client.patch("/api/topics/Old", json={"new_name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_rename_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.patch("/api/topics/Ghost", json={"new_name": "New"})
        assert resp.status_code == 404

    def test_delete_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Doomed")
        resp = client.delete("/api/topics/Doomed")
        assert resp.status_code == 200
        assert topic_mgr.list_topics() == []

    def test_add_item_to_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        resp = client.post("/api/topics/Research/items/proj-1")
        assert resp.status_code == 200
        assert "proj-1" in topic_mgr.list_items("Research")

    def test_add_item_auto_creates_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        resp = client.post("/api/topics/NewTopic/items/proj-1")
        assert resp.status_code == 200
        assert "NewTopic" in topic_mgr.list_topics()

    def test_list_items_in_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "proj-1")
        resp = client.get("/api/topics/Research/items")
        assert resp.status_code == 200
        assert resp.json() == ["proj-1"]

    def test_remove_item_from_topic(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        topic_mgr.add_item("Research", "proj-1")
        resp = client.delete("/api/topics/Research/items/proj-1")
        assert resp.status_code == 200
        assert topic_mgr.list_items("Research") == []

    def test_remove_nonexistent_item_returns_404(self, client: TestClient, topic_mgr: BaseTopicManager) -> None:
        topic_mgr.create("Research")
        resp = client.delete("/api/topics/Research/items/ghost")
        assert resp.status_code == 404
```

**Step 6: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_routes.py::TestCreateItemRouter -v`
Expected: FAIL — `ImportError: cannot import name 'create_item_router'`

**Step 7: Implement `create_item_router` in `routes.py`**

Add to `src/shesha/experimental/shared/routes.py`:

```python
def create_item_router(topic_mgr: Any) -> APIRouter:
    """Create an APIRouter with topic CRUD and item reference routes.

    The *topic_mgr* must implement the ``BaseTopicManager`` interface:
    ``create``, ``rename``, ``delete``, ``list_topics``, ``list_items``,
    ``add_item``, ``remove_item``.
    """
    router = APIRouter(prefix="/api")

    @router.get("/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        names = topic_mgr.list_topics()
        return [
            TopicInfo(
                name=n,
                document_count=len(topic_mgr.list_items(n)),
                size="",
                project_id=f"topic:{n}",
            )
            for n in names
        ]

    @router.post("/topics", status_code=201)
    def create_topic(body: TopicCreate) -> dict[str, str]:
        try:
            topic_mgr.create(body.name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"name": body.name, "project_id": f"topic:{body.name}"}

    @router.patch("/topics/{name}")
    def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
        try:
            topic_mgr.rename(name, body.new_name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"name": body.new_name}

    @router.delete("/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        return {"status": "deleted", "name": name}

    @router.get("/topics/{name}/items")
    def list_topic_items(name: str) -> list[str]:
        try:
            return topic_mgr.list_items(name)
        except ValueError as e:
            raise HTTPException(404, f"Topic '{name}' not found") from e

    @router.post("/topics/{name}/items/{project_id}")
    def add_item_to_topic(name: str, project_id: str) -> dict[str, str]:
        try:
            topic_mgr.create(name)
        except ValueError as e:
            raise HTTPException(_topic_error_to_status(e), str(e)) from e
        topic_mgr.add_item(name, project_id)
        return {"status": "added", "topic": name, "project_id": project_id}

    @router.delete("/topics/{name}/items/{project_id}")
    def remove_item_from_topic(name: str, project_id: str) -> dict[str, str]:
        try:
            topic_mgr.remove_item(name, project_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"status": "removed", "topic": name, "project_id": project_id}

    return router
```

**Step 8: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_routes.py::TestCreateItemRouter tests/unit/experimental/shared/test_routes.py::TestTopicErrorToStatus -v`
Expected: All PASS

**Step 9: Rewrite explorer API files to use shared item router**

**For `document_explorer/api.py`:**
- Remove the topic CRUD section (lines 263-300: `list_topics`, `create_topic`, `rename_topic`, `delete_topic`)
- Remove the topic-document reference section (lines 302-336: `list_topic_docs`, `add_doc_to_topic`, `remove_doc_from_topic`)
- Remove `_build_doc_topic_info` helper (lines 82-93)
- Import and use `create_item_router` from shared routes
- Update `create_api` to include the item router
- Update remaining callers: `upload_documents` uses `topic_mgr.add_item` instead of `add_doc`; `delete_document` uses `remove_item_from_all` instead of `remove_doc_from_all`; `list_uncategorized` uses `list_uncategorized` instead of `list_uncategorized_docs`; `get_document_topics` uses `find_topics_for_item` instead of `find_topics_for_doc`

**For `code_explorer/api.py`:**
- Remove the topic CRUD section (lines 194-228)
- Remove the topic-repo reference section (lines 230-257)
- Remove `_build_code_topic_info` helper (lines 39-50)
- Import and use `create_item_router` from shared routes
- Update `create_api` to include the item router
- Update remaining callers: `add_repo` uses `topic_mgr.add_item` instead of `add_repo`; `delete_repo` uses `remove_item_from_all` instead of `remove_repo_from_all`; `list_uncategorized_repos` uses `list_uncategorized` instead of `list_uncategorized_repos`

**Also update `_resolve_doc_project_ids` and `_resolve_code_project_ids`:**
- Change `list_docs` → `list_items`
- Change `list_repos` → `list_items`

**Step 10: Run full API test suites**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/document_explorer/test_api.py tests/unit/experimental/code_explorer/test_api_topic_repos.py tests/unit/experimental/code_explorer/test_api_repos.py -v`
Expected: Some failures due to route path changes (`/documents/{doc_id}` in topic routes → `/items/{project_id}`)

**Step 11: Update API tests for new route paths**

In `tests/unit/experimental/document_explorer/test_api.py`:
- Change `/api/topics/{name}/documents` → `/api/topics/{name}/items`
- Change `/api/topics/{name}/documents/{doc_id}` → `/api/topics/{name}/items/{doc_id}`
- Update assertions that reference old method names

In `tests/unit/experimental/code_explorer/test_api_topic_repos.py`:
- Change `/api/topics/{name}/repos` → `/api/topics/{name}/items`
- Change `/api/topics/{name}/repos/{project_id}` → `/api/topics/{name}/items/{project_id}`
- Update assertions

**Step 12: Run all API tests again**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/document_explorer/test_api.py tests/unit/experimental/code_explorer/ tests/unit/experimental/shared/test_routes.py -v`
Expected: All PASS

**Step 13: Commit**

```bash
git add src/shesha/experimental/shared/routes.py src/shesha/experimental/document_explorer/api.py src/shesha/experimental/code_explorer/api.py tests/unit/experimental/shared/test_routes.py tests/unit/experimental/document_explorer/test_api.py tests/unit/experimental/code_explorer/
git commit -m "refactor: extract shared topic CRUD and item routes into route factory"
```

---

### Task 5: Shared WebSocket multi-project handler

**Files:**
- Modify: `src/shesha/experimental/shared/websockets.py`
- Modify: `src/shesha/experimental/document_explorer/websockets.py`
- Modify: `src/shesha/experimental/code_explorer/websockets.py`
- Create: `tests/unit/experimental/shared/test_ws_multi.py`

**Step 1: Write failing test for the shared multi-project handler**

Create `tests/unit/experimental/shared/test_ws_multi.py`:

```python
"""Tests for shared multi-project WebSocket handler."""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shesha.experimental.shared.websockets import handle_multi_project_query


@pytest.fixture
def mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.session = MagicMock()
    state.session.format_history_prefix.return_value = ""
    state.shesha._storage.list_documents.return_value = ["doc1.txt"]
    doc = MagicMock()
    doc.content = "Hello"
    doc.name = "doc1.txt"
    state.shesha._storage.get_document.return_value = doc
    project = MagicMock()
    project._rlm_engine = MagicMock()
    result = MagicMock()
    result.answer = "42"
    result.token_usage.prompt_tokens = 10
    result.token_usage.completion_tokens = 5
    result.token_usage.total_tokens = 15
    result.execution_time = 1.5
    project._rlm_engine.query.return_value = result
    state.shesha.get_project.return_value = project
    state.shesha._storage.list_traces.return_value = []
    return state


class TestValidation:
    @pytest.mark.asyncio
    async def test_empty_document_ids_sends_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        data = {"question": "hi", "document_ids": []}
        await handle_multi_project_query(
            mock_ws, data, mock_state, threading.Event(),
            item_noun="documents",
        )
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_id_sends_error(
        self, mock_ws: AsyncMock, mock_state: MagicMock
    ) -> None:
        data = {"question": "hi", "document_ids": ["../evil"]}
        await handle_multi_project_query(
            mock_ws, data, mock_state, threading.Event(),
            item_noun="documents",
        )
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_ws_multi.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement `handle_multi_project_query` in shared websockets**

Add to `src/shesha/experimental/shared/websockets.py`:

```python
import re

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

# Type alias for context builder callback.
# Signature: async def build_context(state, project_ids) -> str
MultiProjectContextBuilder = Callable[[Any, list[str]], Coroutine[Any, Any, str]]


async def handle_multi_project_query(
    ws: WebSocket,
    data: dict[str, Any],
    state: Any,
    cancel_event: threading.Event,
    *,
    item_noun: str = "items",
    build_context: MultiProjectContextBuilder | None = None,
    get_session: Callable[[Any, str], WebConversationSession] | None = None,
) -> None:
    """Execute a cross-project query against multiple projects.

    This is the shared handler for document_explorer and code_explorer
    WebSocket queries.  Each explorer provides an optional *build_context*
    callback for domain-specific context and a *get_session* callback for
    topic-based session resolution.
    """
    question = str(data.get("question", ""))
    document_ids = data.get("document_ids")

    if not document_ids or not isinstance(document_ids, list) or len(document_ids) == 0:
        await ws.send_json(
            {"type": "error", "message": f"Please select one or more {item_noun} before querying"}
        )
        return

    for doc_id in document_ids:
        if not isinstance(doc_id, str) or not _SAFE_ID_RE.match(doc_id):
            await ws.send_json({"type": "error", "message": f"Invalid project id: {doc_id!r}"})
            return

    # Load documents from all requested projects
    loaded_docs: list[ParsedDocument] = []
    loaded_project_ids: list[str] = []
    storage = state.shesha._storage
    for project_id in document_ids:
        pid_str = str(project_id)
        try:
            doc_names = storage.list_documents(pid_str)
        except Exception:
            logger.warning("Could not list documents for project %s", pid_str, exc_info=True)
            continue
        docs_loaded = 0
        for doc_name in doc_names:
            try:
                doc = storage.get_document(pid_str, doc_name)
                loaded_docs.append(doc)
                docs_loaded += 1
            except Exception:
                logger.warning(
                    "Could not load document %s from project %s", doc_name, pid_str, exc_info=True
                )
        if docs_loaded > 0:
            loaded_project_ids.append(pid_str)

    if not loaded_docs:
        await ws.send_json({"type": "error", "message": f"No documents found in selected {item_noun}"})
        return

    # Build context via callback if provided
    context_str = ""
    if build_context is not None:
        context_str = await build_context(state, loaded_project_ids)

    # Resolve session
    topic_name = str(data.get("topic", ""))
    try:
        if topic_name and get_session is not None:
            session = get_session(state, topic_name)
        else:
            session = state.session
    except ValueError:
        await ws.send_json({"type": "error", "message": f"Topic not found: {topic_name}"})
        return

    # Build full question
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question
    if context_str:
        full_question += "\n\n" + context_str

    # Message queue for thread-safe progress
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(
        step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
    ) -> None:
        step_msg: dict[str, object] = {
            "type": "step",
            "step_type": step_type.value,
            "iteration": iteration,
            "content": content,
        }
        if token_usage.prompt_tokens > 0:
            step_msg["prompt_tokens"] = token_usage.prompt_tokens
            step_msg["completion_tokens"] = token_usage.completion_tokens
        loop.call_soon_threadsafe(message_queue.put_nowait, step_msg)

    await ws.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Find RLM engine
    rlm_engine = None
    first_project_id: str | None = None
    for pid in document_ids:
        pid_str = str(pid)
        try:
            project = state.shesha.get_project(pid_str)
        except Exception:
            continue
        if project._rlm_engine is not None:
            rlm_engine = project._rlm_engine
            first_project_id = pid_str
            break

    if rlm_engine is None or first_project_id is None:
        await ws.send_json(
            {"type": "error", "message": f"No valid project found for selected {item_noun}"}
        )
        await message_queue.put(None)
        await drain_task
        return

    try:
        result = await loop.run_in_executor(
            None,
            lambda: rlm_engine.query(
                documents=[d.content for d in loaded_docs],
                question=full_question,
                doc_names=[d.name for d in loaded_docs],
                on_progress=on_progress,
                storage=storage,
                project_id=first_project_id,
                cancel_event=cancel_event,
            ),
        )
    except Exception as exc:
        await message_queue.put(None)
        await drain_task
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    await message_queue.put(None)
    await drain_task

    trace_id = None
    traces = storage.list_traces(first_project_id)
    if traces:
        trace_id = traces[-1].stem

    consulted_ids = loaded_project_ids
    document_bytes = sum(len(d.content.encode("utf-8")) for d in loaded_docs)

    session.add_exchange(
        question=question,
        answer=result.answer,
        trace_id=trace_id,
        tokens={
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        execution_time=result.execution_time,
        model=state.model,
        document_ids=consulted_ids,
    )

    await ws.send_json(
        {
            "type": "complete",
            "answer": result.answer,
            "trace_id": trace_id,
            "tokens": {
                "prompt": result.token_usage.prompt_tokens,
                "completion": result.token_usage.completion_tokens,
                "total": result.token_usage.total_tokens,
            },
            "duration_ms": int(result.execution_time * 1000),
            "document_ids": consulted_ids,
            "document_bytes": document_bytes,
        }
    )
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/shared/test_ws_multi.py -v`
Expected: All PASS

**Step 5: Rewrite explorer WebSocket handlers**

Replace `src/shesha/experimental/document_explorer/websockets.py`:

```python
"""Document explorer WebSocket handler."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from shesha.experimental.shared.websockets import (
    handle_multi_project_query,
    websocket_handler as shared_ws_handler,
)

logger = logging.getLogger(__name__)


async def _build_doc_context(state: Any, project_ids: list[str]) -> str:
    """Build context from upload metadata (filename, content_type)."""
    parts: list[str] = []
    for pid in project_ids:
        meta_path = state.uploads_dir / pid / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                filename = meta.get("filename", pid)
                content_type = meta.get("content_type", "unknown")
                parts.append(f"--- Document: {filename} (type: {content_type}) ---")
            except (OSError, json.JSONDecodeError):
                logger.debug("Skipping unreadable metadata for %s", pid, exc_info=True)
    return "\n\n".join(parts)


async def _handle_query(ws: WebSocket, data: dict, state: Any, cancel_event: Any) -> None:
    await handle_multi_project_query(
        ws, data, state, cancel_event,
        item_noun="documents",
        build_context=_build_doc_context,
        get_session=get_topic_session,
    )


async def websocket_handler(ws: WebSocket, state: DocumentExplorerState) -> None:
    """Handle WebSocket connections for the document explorer."""
    await shared_ws_handler(ws, state, query_handler=_handle_query)
```

Replace `src/shesha/experimental/code_explorer/websockets.py`:

```python
"""Code explorer WebSocket handler."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

from shesha.exceptions import ProjectNotFoundError
from shesha.experimental.code_explorer.dependencies import (
    CodeExplorerState,
    get_topic_session,
)
from shesha.experimental.shared.websockets import (
    handle_multi_project_query,
    websocket_handler as shared_ws_handler,
)

logger = logging.getLogger(__name__)


async def _build_code_context(state: Any, project_ids: list[str]) -> str:
    """Build context from per-project analysis overviews."""
    parts: list[str] = []
    for pid in project_ids:
        try:
            analysis = state.shesha.get_analysis(pid)
        except ProjectNotFoundError:
            logger.warning("Project %s not found, skipping analysis", pid)
            continue
        if analysis is not None:
            parts.append(f"--- Analysis for {pid} ---\n{analysis.overview}")
    return "\n\n".join(parts)


async def _handle_query(ws: WebSocket, data: dict, state: Any, cancel_event: Any) -> None:
    await handle_multi_project_query(
        ws, data, state, cancel_event,
        item_noun="repositories",
        build_context=_build_code_context,
        get_session=get_topic_session,
    )


async def websocket_handler(ws: WebSocket, state: CodeExplorerState) -> None:
    """Handle WebSocket connections for the code explorer."""
    await shared_ws_handler(ws, state, query_handler=_handle_query)
```

**Step 6: Run WebSocket tests**

Run: `source .venv/bin/activate && python -m pytest tests/unit/experimental/document_explorer/test_ws.py tests/unit/experimental/code_explorer/test_ws.py tests/unit/experimental/shared/test_ws_multi.py -v`
Expected: May need minor fixes for import changes or mock adjustments

**Step 7: Fix any test failures and re-run**

Adjust mocks/imports as needed. The key change is that the shared handler now owns the document loading loop, so mocks need to be set up on `state.shesha._storage` consistently.

**Step 8: Commit**

```bash
git add src/shesha/experimental/shared/websockets.py src/shesha/experimental/document_explorer/websockets.py src/shesha/experimental/code_explorer/websockets.py tests/unit/experimental/shared/test_ws_multi.py
git commit -m "refactor: extract shared multi-project WebSocket handler"
```

---

### Task 6: Full test suite verification and cleanup

**Step 1: Run the full test suite**

Run: `source .venv/bin/activate && make all`
Expected: All tests pass, no lint/type errors

**Step 2: Fix any remaining failures**

Address any:
- Import path changes missed in other files
- Type annotation mismatches from `BaseExplorerState` vs subclass
- Frontend API call paths that reference old routes (check `/api/topics/{name}/documents` and `/api/topics/{name}/repos`)

**Step 3: Check frontend for route references**

Run: `grep -r "topics.*documents\|topics.*repos" src/shesha/experimental/document_explorer/frontend/src/ src/shesha/experimental/code_explorer/frontend/src/`

Update any JavaScript/TypeScript fetch calls from:
- `/api/topics/${name}/documents` → `/api/topics/${name}/items`
- `/api/topics/${name}/repos` → `/api/topics/${name}/items`

**Step 4: Run full test suite again after frontend fixes**

Run: `source .venv/bin/activate && make all`
Expected: All pass

**Step 5: Commit cleanup**

```bash
git add -A
git commit -m "fix: update frontend route paths and remaining callers for item routes"
```

---

### Task 7: Delete dead code

**Step 1: Remove duplicated test code**

Now that shared tests cover BaseTopicManager, the per-explorer `test_topics.py` files are mostly redundant. Keep only:
- Tests that verify the subclass is importable and works (1-2 smoke tests each)
- `TestSlugify` can stay in document explorer (it's imported from there) or move to shared

Gut both `test_topics.py` files to just:

```python
"""Smoke tests for DocumentTopicManager/CodeExplorerTopicManager subclass."""

from pathlib import Path
from shesha.experimental.document_explorer.topics import DocumentTopicManager

class TestDocumentTopicManagerSubclass:
    def test_is_usable(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Test")
        assert mgr.list_topics() == ["Test"]
```

(Similar for code explorer.)

**Step 2: Run full suite**

Run: `source .venv/bin/activate && make all`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/unit/experimental/document_explorer/test_topics.py tests/unit/experimental/code_explorer/test_topics.py
git commit -m "refactor: consolidate topic manager tests into shared module"
```

---

### Task 8: Update CHANGELOG.md

**Step 1: Add changelog entry**

Add under `[Unreleased]`:

```markdown
### Changed
- Extracted `BaseTopicManager` into shared module; document and code explorer
  topic managers are now thin subclasses with generic `add_item`/`list_items` API
- Consolidated shared dependencies, API routes, and WebSocket handler across explorers
- On-disk topic format standardized to `"items"` key (breaking change for existing topic data)
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for explorer refactor"
```
