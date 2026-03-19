"""Tests for code explorer repo management API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.exceptions import ProjectNotFoundError, RepoIngestError
from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.models import ProjectInfo, RepoProjectResult


@pytest.fixture
def mock_shesha() -> MagicMock:
    """Create a mock Shesha instance."""
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    # Use a real MagicMock for _storage to allow list_documents calls
    shesha.storage = MagicMock()
    shesha.storage.list_documents.return_value = []
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


# ---- GET /api/repos ----


class TestListRepos:
    def test_empty_list(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos returns empty list when no projects exist."""
        mock_shesha.list_projects.return_value = []
        resp = client.get("/api/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_repos(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos returns RepoInfo dicts for each project."""
        mock_shesha.list_projects.return_value = ["owner-myrepo"]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="missing",
        )
        mock_shesha.storage.list_documents.return_value = ["file1.py", "file2.py", "file3.py"]

        resp = client.get("/api/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        repo = data[0]
        assert repo["project_id"] == "owner-myrepo"
        assert repo["source_url"] == "https://github.com/owner/myrepo"
        assert repo["file_count"] == 3
        assert repo["analysis_status"] == "missing"

    def test_list_multiple_repos(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos returns info for multiple projects."""
        mock_shesha.list_projects.return_value = ["repo-a", "repo-b"]
        mock_shesha.get_project_info.side_effect = [
            ProjectInfo(
                project_id="repo-a",
                source_url="https://github.com/x/a",
                is_local=False,
                source_exists=True,
                analysis_status="current",
            ),
            ProjectInfo(
                project_id="repo-b",
                source_url="/home/user/b",
                is_local=True,
                source_exists=True,
                analysis_status="stale",
            ),
        ]
        mock_shesha.storage.list_documents.side_effect = [["f1"], ["f2", "f3"]]

        resp = client.get("/api/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["project_id"] == "repo-a"
        assert data[0]["file_count"] == 1
        assert data[1]["project_id"] == "repo-b"
        assert data[1]["file_count"] == 2


# ---- GET /api/repos/uncategorized ----


class TestListUncategorizedRepos:
    def test_all_uncategorized(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos/uncategorized returns all repos when none are in topics."""
        mock_shesha.list_projects.return_value = ["repo-a"]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="repo-a",
            source_url="https://github.com/x/a",
            is_local=False,
            source_exists=True,
            analysis_status="missing",
        )
        mock_shesha.storage.list_documents.return_value = ["f1"]

        resp = client.get("/api/repos/uncategorized")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "repo-a"

    def test_excludes_categorized_repos(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/repos/uncategorized excludes repos that are in any topic."""
        topic_mgr.create("RLMs")
        topic_mgr.add_item("RLMs", "repo-a")

        mock_shesha.list_projects.return_value = ["repo-a", "repo-b"]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="repo-b",
            source_url="https://github.com/x/b",
            is_local=False,
            source_exists=True,
            analysis_status="missing",
        )
        mock_shesha.storage.list_documents.return_value = ["f1"]

        resp = client.get("/api/repos/uncategorized")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "repo-b"

    def test_empty_when_all_categorized(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """GET /api/repos/uncategorized returns empty list when all repos are in topics."""
        topic_mgr.create("RLMs")
        topic_mgr.add_item("RLMs", "repo-a")

        mock_shesha.list_projects.return_value = ["repo-a"]

        resp = client.get("/api/repos/uncategorized")
        assert resp.status_code == 200
        assert resp.json() == []


# ---- POST /api/repos ----


class TestAddRepo:
    def test_add_new_repo(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """POST /api/repos adds a new repo and returns project info."""
        project = MagicMock()
        project.project_id = "owner-myrepo"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="created",
            files_ingested=42,
        )

        resp = client.post("/api/repos", json={"url": "https://github.com/owner/myrepo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "owner-myrepo"
        assert data["status"] == "created"
        assert data["files_ingested"] == 42
        mock_shesha.create_project_from_repo.assert_called_once_with(
            "https://github.com/owner/myrepo"
        )

    def test_add_repo_with_topic(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """POST /api/repos with topic creates topic and adds repo reference."""
        project = MagicMock()
        project.project_id = "owner-myrepo"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="created",
            files_ingested=10,
        )

        resp = client.post(
            "/api/repos",
            json={"url": "https://github.com/owner/myrepo", "topic": "Frontend"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "owner-myrepo"

        # Topic should have been created and repo added
        assert "Frontend" in topic_mgr.list_topics()
        assert "owner-myrepo" in topic_mgr.list_items("Frontend")

    def test_add_duplicate_url_returns_existing(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """POST /api/repos with existing URL returns unchanged status."""
        project = MagicMock()
        project.project_id = "owner-myrepo"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="unchanged",
            files_ingested=42,
        )

        resp = client.post("/api/repos", json={"url": "https://github.com/owner/myrepo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unchanged"

    def test_add_repo_clone_error_returns_422(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """POST /api/repos returns 422 when clone fails (e.g. directory exists)."""
        mock_shesha.create_project_from_repo.side_effect = RepoIngestError(
            "https://github.com/owner/myrepo",
            RuntimeError("destination path already exists"),
        )

        resp = client.post("/api/repos", json={"url": "https://github.com/owner/myrepo"})
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data

    def test_add_repo_error_does_not_leak_internal_paths(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """RepoIngestError with git stderr must not leak internal filesystem paths."""
        # Simulate git stderr that includes internal paths
        stderr_msg = (
            "fatal: could not create work tree dir "
            "'/var/lib/shesha/repos/myrepo': Permission denied"
        )
        mock_shesha.create_project_from_repo.side_effect = RepoIngestError(
            "https://github.com/owner/myrepo",
            RuntimeError(stderr_msg),
        )

        resp = client.post("/api/repos", json={"url": "https://github.com/owner/myrepo"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "/var/lib/shesha/repos" not in detail


# ---- GET /api/repos/{id} ----


class TestGetRepo:
    def test_get_repo_found(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos/{id} returns RepoInfo for existing project."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        mock_shesha.storage.list_documents.return_value = ["a.py", "b.py"]

        resp = client.get("/api/repos/owner-myrepo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "owner-myrepo"
        assert data["source_url"] == "https://github.com/owner/myrepo"
        assert data["file_count"] == 2
        assert data["analysis_status"] == "current"

    def test_get_repo_not_found(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """GET /api/repos/{id} returns 404 for missing project."""
        mock_shesha.get_project_info.side_effect = ProjectNotFoundError("nonexistent")

        resp = client.get("/api/repos/nonexistent")
        assert resp.status_code == 404


# ---- DELETE /api/repos/{id} ----


class TestDeleteRepo:
    def test_delete_repo(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """DELETE /api/repos/{id} removes from topics and deletes project."""
        # Set up a topic referencing the project
        topic_mgr.create("Backend")
        topic_mgr.add_item("Backend", "owner-myrepo")

        resp = client.delete("/api/repos/owner-myrepo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["project_id"] == "owner-myrepo"

        # Should have been removed from topic
        assert "owner-myrepo" not in topic_mgr.list_items("Backend")

        # Should have called shesha.delete_project
        mock_shesha.delete_project.assert_called_once_with("owner-myrepo", cleanup_repo=True)

    def test_delete_repo_removes_from_multiple_topics(
        self,
        client: TestClient,
        mock_shesha: MagicMock,
        topic_mgr: CodeExplorerTopicManager,
    ) -> None:
        """DELETE removes repo references from all topics."""
        topic_mgr.create("Frontend")
        topic_mgr.create("Backend")
        topic_mgr.add_item("Frontend", "owner-myrepo")
        topic_mgr.add_item("Backend", "owner-myrepo")

        resp = client.delete("/api/repos/owner-myrepo")
        assert resp.status_code == 200

        assert "owner-myrepo" not in topic_mgr.list_items("Frontend")
        assert "owner-myrepo" not in topic_mgr.list_items("Backend")

    def test_delete_repo_not_found(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """DELETE returns 404 for nonexistent project."""
        mock_shesha.get_project_info.side_effect = ProjectNotFoundError("nonexistent")

        resp = client.delete("/api/repos/nonexistent")
        assert resp.status_code == 404


# ---- POST /api/repos/{id}/check-updates ----


class TestCheckUpdates:
    def test_check_updates_unchanged(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """check-updates returns unchanged when no updates available."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        project = MagicMock()
        project.project_id = "owner-myrepo"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="unchanged",
            files_ingested=10,
        )

        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unchanged"
        assert data["files_ingested"] == 10

    def test_check_updates_available(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """check-updates returns updates_available when upstream changed."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        project = MagicMock()
        project.project_id = "owner-myrepo"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=lambda: RepoProjectResult(
                project=project, status="created", files_ingested=15
            ),
        )

        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updates_available"
        assert data["files_ingested"] == 10

    def test_check_updates_not_found(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """check-updates returns 404 for missing project."""
        mock_shesha.get_project_info.side_effect = ProjectNotFoundError("nonexistent")

        resp = client.post("/api/repos/nonexistent/check-updates")
        assert resp.status_code == 404

    def test_check_updates_clone_error_returns_422(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """check-updates returns 422 when create_project_from_repo raises RepoIngestError."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        mock_shesha.create_project_from_repo.side_effect = RepoIngestError(
            "https://github.com/owner/myrepo",
            RuntimeError("network timeout"),
        )

        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_check_updates_no_source_url(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """check-updates returns 400 when project has no source URL."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url=None,
            is_local=False,
            source_exists=True,
            analysis_status="missing",
        )

        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 400


# ---- POST /api/repos/{id}/apply-updates ----


class TestApplyUpdates:
    def test_apply_updates(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """apply-updates calls apply_updates() and returns new status."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        project = MagicMock()
        project.project_id = "owner-myrepo"

        # First, check-updates must store the result
        updated_result = RepoProjectResult(
            project=project,
            status="created",
            files_ingested=25,
        )
        check_result = RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=lambda: updated_result,
        )
        mock_shesha.create_project_from_repo.return_value = check_result

        # First check for updates (this stores the result)
        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 200
        assert resp.json()["status"] == "updates_available"

        # Now apply updates
        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["files_ingested"] == 25

    def test_apply_updates_self_heals_without_check(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """apply-updates re-derives and applies when cache is empty."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
        )

        project = MagicMock()
        project.project_id = "owner-myrepo"

        updated_result = RepoProjectResult(
            project=project,
            status="created",
            files_ingested=30,
        )

        # First call returns updates_available with apply fn,
        # apply fn returns the updated result
        check_result = RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=lambda: updated_result,
        )
        mock_shesha.create_project_from_repo.return_value = check_result

        # Call apply-updates directly without check-updates
        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["files_ingested"] == 30

    def test_apply_updates_no_source_url(self, client: TestClient, mock_shesha: MagicMock) -> None:
        """apply-updates returns 400 when project has no source URL and cache is empty."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url=None,
            is_local=False,
            source_exists=False,
        )
        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 400

    def test_apply_updates_unchanged_returns_409(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """apply-updates returns 409 when re-check finds no updates."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
        )

        project = MagicMock()
        project.project_id = "owner-myrepo"

        # Re-derive finds unchanged
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="unchanged",
            files_ingested=10,
        )

        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 409

    def test_apply_updates_self_heal_clone_error_returns_422(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """apply-updates self-heal returns 422 when clone fails."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
        )
        mock_shesha.create_project_from_repo.side_effect = RepoIngestError(
            "https://github.com/owner/myrepo",
            RuntimeError("network timeout"),
        )

        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_apply_updates_call_raises_repo_ingest_error_returns_422(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """apply-updates returns 422 when apply_updates() raises RepoIngestError."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="owner-myrepo",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )
        project = MagicMock()
        project.project_id = "owner-myrepo"

        # check-updates returns updates_available, but apply_updates raises
        check_result = RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=lambda: (_ for _ in ()).throw(
                RepoIngestError("https://github.com/owner/myrepo", RuntimeError("pull failed"))
            ),
        )
        mock_shesha.create_project_from_repo.return_value = check_result

        # First check for updates
        resp = client.post("/api/repos/owner-myrepo/check-updates")
        assert resp.status_code == 200

        # Now apply — should get 422, not 500
        resp = client.post("/api/repos/owner-myrepo/apply-updates")
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_check_updates_passes_project_id_as_name(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """check-updates passes name=project_id so the correct project is checked."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="custom-name",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
        )
        project = MagicMock()
        project.project_id = "custom-name"
        mock_shesha.create_project_from_repo.return_value = RepoProjectResult(
            project=project,
            status="unchanged",
            files_ingested=5,
        )

        client.post("/api/repos/custom-name/check-updates")

        mock_shesha.create_project_from_repo.assert_called_once_with(
            "https://github.com/owner/myrepo", name="custom-name"
        )

    def test_apply_updates_self_heal_passes_project_id_as_name(
        self, client: TestClient, mock_shesha: MagicMock
    ) -> None:
        """apply-updates self-heal passes name=project_id to re-derive correctly."""
        mock_shesha.get_project_info.return_value = ProjectInfo(
            project_id="custom-name",
            source_url="https://github.com/owner/myrepo",
            is_local=False,
            source_exists=True,
        )
        project = MagicMock()
        project.project_id = "custom-name"
        check_result = RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=lambda: RepoProjectResult(
                project=project,
                status="created",
                files_ingested=20,
            ),
        )
        mock_shesha.create_project_from_repo.return_value = check_result

        client.post("/api/repos/custom-name/apply-updates")

        mock_shesha.create_project_from_repo.assert_called_once_with(
            "https://github.com/owner/myrepo", name="custom-name"
        )
