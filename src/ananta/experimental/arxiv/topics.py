"""Topic management backed by Shesha projects."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from shesha.exceptions import ProjectExistsError, ProjectNotFoundError
from shesha.experimental.arxiv.models import TopicInfo

if TYPE_CHECKING:
    from pathlib import Path

    from shesha import Shesha
    from shesha.storage.filesystem import FilesystemStorage


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    # Replace punctuation that acts as word separators with spaces
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class TopicManager:
    """Manage topics backed by Shesha projects."""

    TOPIC_META_FILE = "_topic.json"

    def __init__(
        self,
        shesha: Shesha,
        storage: FilesystemStorage,
    ) -> None:
        self._shesha = shesha
        self._storage = storage

    @property
    def storage(self) -> FilesystemStorage:
        """The storage backend used by this topic manager."""
        return self._storage

    def create(self, name: str) -> str:
        """Create a new topic, or return existing project ID if it already exists."""
        slug = slugify(name)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        project_id = f"{today}-{slug}"
        try:
            self._storage.create_project(project_id)
        except ProjectExistsError:
            # Ensure _topic.json exists (may be missing from a prior bug)
            meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
            if not meta_path.exists():
                topic_meta = {
                    "name": slug,
                    "created": datetime.now(tz=UTC).isoformat(),
                }
                meta_path.write_text(json.dumps(topic_meta, indent=2))
            return project_id
        # Write topic metadata
        topic_meta = {
            "name": slug,
            "created": datetime.now(tz=UTC).isoformat(),
        }
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        meta_path.write_text(json.dumps(topic_meta, indent=2))
        return project_id

    def list_topics(self) -> list[TopicInfo]:
        """List all topics with metadata."""
        topics = []
        for project_id in self._storage.list_projects():
            info = self._read_topic_info(project_id)
            if info is not None:
                topics.append(info)
        return sorted(topics, key=lambda t: t.created)

    def delete(self, name: str) -> None:
        """Delete a topic by slug name."""
        project_id = self.resolve(name)
        if project_id is None:
            msg = f"Topic not found: {name}"
            raise ValueError(msg)
        self._storage.delete_project(project_id)

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a topic's display name (does not rename the directory)."""
        project_id = self.resolve(old_name)
        if project_id is None:
            msg = f"Topic not found: {old_name}"
            raise ValueError(msg)
        meta = self._read_topic_meta(project_id)
        assert meta is not None  # resolve guarantees this
        meta["name"] = slugify(new_name)
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        meta_path.write_text(json.dumps(meta, indent=2))

    def resolve(self, name: str) -> str | None:
        """Resolve a topic slug to its full project ID."""
        slug = slugify(name)
        for project_id in self._storage.list_projects():
            meta = self._read_topic_meta(project_id)
            if meta is not None and meta.get("name") == slug:
                return project_id
        return None

    def get_topic_info(self, name: str) -> TopicInfo | None:
        """Get info for a specific topic."""
        project_id = self.resolve(name)
        if project_id is None:
            return None
        return self._read_topic_info(project_id)

    def get_topic_info_by_project_id(self, project_id: str) -> TopicInfo | None:
        """Get topic info directly from a project ID."""
        if not self._storage.project_exists(project_id):
            return None
        return self._read_topic_info(project_id)

    def _read_topic_info(self, project_id: str) -> TopicInfo | None:
        """Read topic info from a project directory."""
        meta = self._read_topic_meta(project_id)
        if meta is None:
            return None
        docs = self._storage.list_documents(project_id)
        size = self._compute_size(project_id)
        created = datetime.fromisoformat(meta["created"])
        return TopicInfo(
            name=meta["name"],
            created=created,
            paper_count=len(docs),
            size_bytes=size,
            project_id=project_id,
        )

    def get_doc_order(self, project_id: str) -> list[str] | None:
        """Return the stored document order for a project, or None if unset."""
        try:
            meta = self._read_topic_meta(project_id)
        except ProjectNotFoundError:
            return None
        if meta is None:
            return None
        order = meta.get("doc_order")
        if order is None:
            return None
        return list(order)

    def set_doc_order(self, project_id: str, order: list[str]) -> None:
        """Store a custom document order in the topic metadata."""
        meta = self._read_topic_meta(project_id)
        if meta is None:
            msg = f"Topic metadata not found for project: {project_id}"
            raise ValueError(msg)
        meta["doc_order"] = order
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        meta_path.write_text(json.dumps(meta, indent=2))

    def _read_topic_meta(self, project_id: str) -> dict[str, Any] | None:
        """Read the _topic.json for a project, or None if not a topic."""
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text())  # type: ignore[no-any-return]

    def _compute_size(self, project_id: str) -> int:
        """Compute total size on disk for a project."""
        project_path = self._project_path(project_id)
        total = 0
        for dirpath, _dirnames, filenames in os.walk(project_path):
            for filename in filenames:
                total += os.path.getsize(os.path.join(dirpath, filename))
        return total

    def _project_path(self, project_id: str) -> Path:
        """Get the filesystem path for a project."""
        return self._storage.get_project_dir(project_id)
