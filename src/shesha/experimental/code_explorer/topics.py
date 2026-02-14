"""Topic management for the code explorer.

Topics are lightweight reference containers that hold project_id strings
pointing to repos. A repo can appear in zero or more topics. Deleting a
topic removes the references but not the repos themselves.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TypedDict

TOPIC_META_FILE = "topic.json"


class _TopicMeta(TypedDict):
    """Schema for topic.json files."""

    name: str
    repos: list[str]


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    # Replace punctuation that acts as word separators with spaces
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class CodeExplorerTopicManager:
    """Manages topics as lightweight reference containers for repos.

    Each topic is a directory inside *topics_dir* containing a ``topic.json``
    file with the structure::

        {"name": "Frontend", "repos": ["project-id-1", "project-id-2"]}

    The directory name is a slugified version of the display name.
    """

    def __init__(self, topics_dir: Path) -> None:
        self._topics_dir = topics_dir
        self._topics_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Topic CRUD
    # ------------------------------------------------------------------

    def create(self, name: str) -> None:
        """Create a new topic.  Idempotent — no error if it already exists."""
        slug = _slugify(name)
        topic_dir = self._topics_dir / slug
        meta_path = topic_dir / TOPIC_META_FILE

        if meta_path.exists():
            return  # already exists

        topic_dir.mkdir(parents=True, exist_ok=True)
        meta: _TopicMeta = {"name": name, "repos": []}
        meta_path.write_text(json.dumps(meta, indent=2))

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a topic's display name (directory stays the same)."""
        meta, meta_path = self._resolve(old_name)
        meta["name"] = new_name
        meta_path.write_text(json.dumps(meta, indent=2))

    def delete(self, name: str) -> None:
        """Delete a topic and its directory.  Repos are not affected."""
        _meta, meta_path = self._resolve(name)
        shutil.rmtree(meta_path.parent)

    def list_topics(self) -> list[str]:
        """Return display names of all topics, sorted alphabetically."""
        names: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None:
                names.append(meta["name"])
        return sorted(names)

    # ------------------------------------------------------------------
    # Repo references
    # ------------------------------------------------------------------

    def add_repo(self, topic: str, project_id: str) -> None:
        """Add a repo reference to a topic.  Idempotent."""
        meta, meta_path = self._resolve(topic)
        repos = meta["repos"]
        if project_id not in repos:
            repos.append(project_id)
            meta_path.write_text(json.dumps(meta, indent=2))

    def remove_repo(self, topic: str, project_id: str) -> None:
        """Remove a repo reference from a topic."""
        meta, meta_path = self._resolve(topic)
        repos = meta["repos"]
        if project_id not in repos:
            msg = f"Repo not found in topic '{topic}': {project_id}"
            raise ValueError(msg)
        repos.remove(project_id)
        meta_path.write_text(json.dumps(meta, indent=2))

    def list_repos(self, topic: str) -> list[str]:
        """Return project_ids referenced by a topic."""
        meta, _meta_path = self._resolve(topic)
        return list(meta["repos"])

    def list_all_repos(self) -> list[str]:
        """Return unique project_ids across all topics."""
        seen: set[str] = set()
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            for repo in meta["repos"]:
                if repo not in seen:
                    seen.add(repo)
                    result.append(repo)
        return result

    def list_uncategorized_repos(self, all_project_ids: list[str]) -> list[str]:
        """Return project_ids from *all_project_ids* not in any topic."""
        categorized = set(self.list_all_repos())
        return [pid for pid in all_project_ids if pid not in categorized]

    def find_topics_for_repo(self, project_id: str) -> list[str]:
        """Return display names of all topics that contain *project_id*."""
        result: list[str] = []
        for topic_dir in self._iter_topic_dirs():
            meta = self._read_meta(topic_dir)
            if meta is not None and project_id in meta["repos"]:
                result.append(meta["name"])
        return sorted(result)

    def remove_repo_from_all(self, project_id: str) -> None:
        """Remove *project_id* from every topic that contains it."""
        for topic_dir in self._iter_topic_dirs():
            meta_path = topic_dir / TOPIC_META_FILE
            meta = self._read_meta(topic_dir)
            if meta is None:
                continue
            repos = meta["repos"]
            if project_id in repos:
                repos.remove(project_id)
                meta_path.write_text(json.dumps(meta, indent=2))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, name: str) -> tuple[_TopicMeta, Path]:
        """Find a topic by display name and return (meta_dict, meta_path).

        Raises ``ValueError`` if the topic does not exist.
        """
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
            return json.loads(meta_path.read_text())  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            return None  # Corrupt file — treat as missing
