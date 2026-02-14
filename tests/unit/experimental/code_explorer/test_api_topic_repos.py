"""Tests for code explorer topic-repo reference API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager


@pytest.fixture
def mock_shesha() -> MagicMock:
    """Create a mock Shesha instance."""
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha._storage = MagicMock()
    shesha._storage.list_documents.return_value = []
    return shesha


@pytest.fixture
def topic_mgr(tmp_path: Path) -> CodeExplorerTopicManager:
    """Create a real CodeExplorerTopicManager backed by tmp_path."""
    return CodeExplorerTopicManager(tmp_path / "topics")


@pytest.fixture
def state(mock_shesha: MagicMock, topic_mgr: CodeExplorerTopicManager) -> CodeExplorerState:
    """Create a CodeExplorerState with mock shesha and real topic manager."""
    return CodeExplorerState(
        shesha=mock_shesha,
        topic_mgr=topic_mgr,
        session=MagicMock(),
        model="test-model",
    )


@pytest.fixture
def client(state: CodeExplorerState) -> TestClient:
    """Create a FastAPI TestClient for the code explorer API."""
    app = create_api(state)
    return TestClient(app)


# ---- POST /api/topics/{name}/repos/{project_id} ----


class TestAddRepoToTopic:
    def test_add_repo_to_existing_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """POST /api/topics/{name}/repos/{id} adds repo reference to topic."""
        topic_mgr.create("Frontend")

        resp = client.post("/api/topics/Frontend/repos/owner-myrepo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "added"
        assert data["topic"] == "Frontend"
        assert data["project_id"] == "owner-myrepo"

        # Verify the repo is actually in the topic
        assert "owner-myrepo" in topic_mgr.list_repos("Frontend")

    def test_auto_creates_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """POST /api/topics/{name}/repos/{id} creates topic if it doesn't exist."""
        # Topic does not exist yet
        assert "NewTopic" not in topic_mgr.list_topics()

        resp = client.post("/api/topics/NewTopic/repos/owner-myrepo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "added"
        assert data["topic"] == "NewTopic"

        # Topic should have been auto-created
        assert "NewTopic" in topic_mgr.list_topics()
        assert "owner-myrepo" in topic_mgr.list_repos("NewTopic")

    def test_idempotent_add(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """POST /api/topics/{name}/repos/{id} is idempotent (adding twice is fine)."""
        topic_mgr.create("Backend")

        resp1 = client.post("/api/topics/Backend/repos/owner-myrepo")
        assert resp1.status_code == 200

        resp2 = client.post("/api/topics/Backend/repos/owner-myrepo")
        assert resp2.status_code == 200

        # Should only appear once in the topic
        repos = topic_mgr.list_repos("Backend")
        assert repos.count("owner-myrepo") == 1


# ---- DELETE /api/topics/{name}/repos/{project_id} ----


class TestRemoveRepoFromTopic:
    def test_remove_repo_from_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """DELETE /api/topics/{name}/repos/{id} removes repo reference."""
        topic_mgr.create("Frontend")
        topic_mgr.add_repo("Frontend", "owner-myrepo")

        resp = client.delete("/api/topics/Frontend/repos/owner-myrepo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "removed"
        assert data["topic"] == "Frontend"
        assert data["project_id"] == "owner-myrepo"

        # Repo should no longer be in the topic
        assert "owner-myrepo" not in topic_mgr.list_repos("Frontend")

    def test_removing_last_reference_does_not_delete_repo(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """DELETE does NOT delete the repo from shesha even when it's the last reference."""
        topic_mgr.create("Frontend")
        topic_mgr.add_repo("Frontend", "owner-myrepo")

        resp = client.delete("/api/topics/Frontend/repos/owner-myrepo")
        assert resp.status_code == 200

        # Shesha.delete_project should NOT have been called
        mock_shesha.delete_project.assert_not_called()

    def test_remove_repo_topic_not_found(
        self,
        client: TestClient,
    ) -> None:
        """DELETE returns 404 when topic doesn't exist."""
        resp = client.delete("/api/topics/NonExistent/repos/owner-myrepo")
        assert resp.status_code == 404

    def test_remove_repo_not_in_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """DELETE returns 404 when repo is not in the topic."""
        topic_mgr.create("Frontend")

        resp = client.delete("/api/topics/Frontend/repos/owner-myrepo")
        assert resp.status_code == 404
