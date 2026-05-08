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

    # Topic names are human-readable labels stored verbatim in topic.json
    # and rendered in UI sidebars. The cap is generous for a label but well
    # below anything that would bloat the topic store or break layout.
    MAX_TOPIC_NAME_LEN = 256

    _CONTROL_BYTES_RE = re.compile(r"[\x00-\x1f\x7f]")

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Strip surrounding whitespace from a topic name (I12).

        Without this, ``"Reports "`` and ``"Reports"`` produced two topics
        that slugified to the same directory but stored different display
        names, so the second call's ``_resolve`` failed to find the first's
        topic. Normalising at every entry point keeps lookup symmetric.
        """
        return name.strip()

    @classmethod
    def _validate_name(cls, name: str) -> None:
        """Reject names that contain path separators, control bytes, or
        exceed the length cap (I5)."""
        if "/" in name or "\\" in name:
            msg = f"Topic name must not contain a path separator: {name!r}"
            raise ValueError(msg)
        if cls._CONTROL_BYTES_RE.search(name):
            msg = f"Topic name must not contain control characters: {name!r}"
            raise ValueError(msg)
        if len(name) > cls.MAX_TOPIC_NAME_LEN:
            msg = (
                f"Topic name is too long ({len(name)} chars; max "
                f"{cls.MAX_TOPIC_NAME_LEN}): {name[:32]!r}…"
            )
            raise ValueError(msg)

    def create(self, name: str) -> None:
        """Create a new topic.  Idempotent -- no error if it already exists."""
        name = self._normalize_name(name)
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
        old_name = self._normalize_name(old_name)
        new_name = self._normalize_name(new_name)
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

    def resolve(self, name: str) -> str | None:
        """Resolve a topic name to its first project_id, or None."""
        try:
            meta, _path = self._resolve(name)
        except ValueError:
            return None
        items = meta["items"]
        return items[0] if items else None

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

    def reorder_items(self, topic: str, item_ids: list[str]) -> None:
        """Reorder items in a topic. *item_ids* must contain exactly the same IDs."""
        meta, meta_path = self._resolve(topic)
        existing = set(meta["items"])
        new = set(item_ids)
        if existing != new:
            msg = (
                f"item_ids must contain exactly the same items as the topic "
                f"(got {len(item_ids)}, expected {len(existing)})"
            )
            raise ValueError(msg)
        meta["items"] = list(item_ids)
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
        """Find a topic by display name and return (meta_dict, meta_path).

        Names are matched against the stored display name after both sides
        are stripped (I12) — so a topic stored as ``"Reports"`` resolves
        when looked up as ``"  Reports "`` or vice versa.
        """
        name = self._normalize_name(name)
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
