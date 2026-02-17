"""Tests for code explorer topic-repo reference API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.models import ProjectInfo


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


# ---- GET /api/topics/{name}/repos ----


class TestListTopicRepos:
    def test_list_repos_in_topic(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/topics/{name}/repos returns RepoInfo for repos in topic."""
        topic_mgr.create("RLMs")
        topic_mgr.add_repo("RLMs", "owner-myrepo")

        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        mock_shesha._storage.list_documents.return_value = ["a.py", "b.py"]

        resp = client.get("/api/topics/RLMs/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "owner-myrepo"
        assert data[0]["file_count"] == 2

    def test_list_repos_empty_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/topics/{name}/repos returns empty list for topic with no repos."""
        topic_mgr.create("Empty")

        resp = client.get("/api/topics/Empty/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_repos_topic_not_found(self, client: TestClient) -> None:
        """GET /api/topics/{name}/repos returns 404 for missing topic."""
        resp = client.get("/api/topics/NonExistent/repos")
        assert resp.status_code == 404

    def test_excludes_repos_not_in_topic(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/topics/{name}/repos only returns repos in that specific topic."""
        topic_mgr.create("RLMs")
        topic_mgr.create("Other")
        topic_mgr.add_repo("RLMs", "repo-a")
        topic_mgr.add_repo("Other", "repo-b")

        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="repo-a",
            source_url="https://github.com/x/a",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        mock_shesha._storage.list_documents.return_value = ["f1"]

        resp = client.get("/api/topics/RLMs/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "repo-a"


# ---- GET /api/topics (project_id uniqueness) ----


class TestListTopicsUniqueIds:
    def test_topics_have_unique_project_ids(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/topics returns unique project_id for each topic (React key)."""
        topic_mgr.create("RLMs")
        topic_mgr.create("Frontend")

        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        ids = [t["project_id"] for t in data]
        # All project_ids must be non-empty and unique
        assert all(pid for pid in ids), f"Empty project_id found: {ids}"
        assert len(set(ids)) == len(ids), f"Duplicate project_ids: {ids}"


# ---- PATCH /api/topics/{name} (rename) ----


class TestRenameTopic:
    def test_rename_topic(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """PATCH /api/topics/{name} renames a topic."""
        topic_mgr.create("Old")
        resp = client.patch("/api/topics/Old", json={"new_name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"
        assert "New" in topic_mgr.list_topics()

    def test_rename_nonexistent_returns_404(self, client: TestClient) -> None:
        """PATCH /api/topics/{name} returns 404 when topic doesn't exist."""
        resp = client.patch("/api/topics/Ghost", json={"new_name": "New"})
        assert resp.status_code == 404

    def test_rename_to_existing_name_returns_409(
        self,
        client: TestClient,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """PATCH /api/topics/{name} returns 409 when new name conflicts."""
        topic_mgr.create("Alpha")
        topic_mgr.create("Beta")
        resp = client.patch("/api/topics/Alpha", json={"new_name": "Beta"})
        assert resp.status_code == 409
