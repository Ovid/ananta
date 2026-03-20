"""Tests for code explorer analysis API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ananta.exceptions import ProjectNotFoundError
from ananta.experimental.code_explorer.api import create_api
from ananta.experimental.code_explorer.dependencies import CodeExplorerState
from ananta.experimental.code_explorer.topics import CodeExplorerTopicManager
from ananta.models import AnalysisComponent, AnalysisExternalDep, RepoAnalysis


@pytest.fixture
def mock_ananta(tmp_path: Path) -> MagicMock:
    """Create a mock Ananta instance."""
    ananta = MagicMock()
    ananta.list_projects.return_value = []
    ananta.storage = MagicMock()
    ananta.storage.list_documents.return_value = []
    # Return a real Path so _build_repo_info's display-name lookup doesn't
    # produce a MagicMock string.  Individual tests can override this.
    ananta.storage.get_project_dir.return_value = tmp_path / "default_project_dir"
    return ananta


@pytest.fixture
def topic_mgr(tmp_path: Path) -> CodeExplorerTopicManager:
    """Create a real CodeExplorerTopicManager backed by tmp_path."""
    return CodeExplorerTopicManager(tmp_path / "topics")


@pytest.fixture
def state(mock_ananta: MagicMock, topic_mgr: CodeExplorerTopicManager) -> CodeExplorerState:
    """Create a CodeExplorerState with mock ananta and real topic manager."""
    return CodeExplorerState(
        ananta=mock_ananta,
        topic_mgr=topic_mgr,
        session=MagicMock(),
        model="test-model",
    )


@pytest.fixture
def client(state: CodeExplorerState) -> TestClient:
    """Create a FastAPI TestClient for the code explorer API."""
    app = create_api(state)
    return TestClient(app)


def _make_analysis() -> RepoAnalysis:
    """Create a sample RepoAnalysis for testing."""
    return RepoAnalysis(
        version="1",
        generated_at="2025-01-01T00:00:00Z",
        head_sha="abc123",
        overview="A test project overview.",
        components=[
            AnalysisComponent(
                name="core",
                path="src/core",
                description="Core module",
                apis=[{"method": "GET", "path": "/health"}],
                models=["User"],
                entry_points=["main.py"],
                internal_dependencies=["utils"],
            ),
        ],
        external_dependencies=[
            AnalysisExternalDep(
                name="PostgreSQL",
                type="database",
                description="Primary data store",
                used_by=["core"],
            ),
        ],
        caveats="Test caveats.",
    )


# ---- POST /api/repos/{id}/analyze ----


class TestGenerateAnalysis:
    def test_generate_analysis_success(self, client: TestClient, mock_ananta: MagicMock) -> None:
        """POST /api/repos/{id}/analyze returns AnalysisResponse on success."""
        analysis = _make_analysis()
        mock_ananta.generate_analysis.return_value = analysis

        resp = client.post("/api/repos/owner-myrepo/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1"
        assert data["generated_at"] == "2025-01-01T00:00:00Z"
        assert data["head_sha"] == "abc123"
        assert data["overview"] == "A test project overview."
        assert len(data["components"]) == 1
        assert data["components"][0]["name"] == "core"
        assert len(data["external_dependencies"]) == 1
        assert data["external_dependencies"][0]["name"] == "PostgreSQL"
        assert data["caveats"] == "Test caveats."
        mock_ananta.generate_analysis.assert_called_once_with("owner-myrepo")

    def test_generate_analysis_project_not_found(
        self, client: TestClient, mock_ananta: MagicMock
    ) -> None:
        """POST /api/repos/{id}/analyze returns 404 for missing project."""
        mock_ananta.generate_analysis.side_effect = ProjectNotFoundError("nonexistent")

        resp = client.post("/api/repos/nonexistent/analyze")
        assert resp.status_code == 404


# ---- GET /api/repos/{id}/analysis ----


class TestGetAnalysis:
    def test_get_analysis_success(self, client: TestClient, mock_ananta: MagicMock) -> None:
        """GET /api/repos/{id}/analysis returns AnalysisResponse when analysis exists."""
        analysis = _make_analysis()
        mock_ananta.get_analysis.return_value = analysis

        resp = client.get("/api/repos/owner-myrepo/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1"
        assert data["generated_at"] == "2025-01-01T00:00:00Z"
        assert data["head_sha"] == "abc123"
        assert data["overview"] == "A test project overview."
        assert len(data["components"]) == 1
        assert data["components"][0]["name"] == "core"
        assert len(data["external_dependencies"]) == 1
        assert data["external_dependencies"][0]["name"] == "PostgreSQL"
        assert data["caveats"] == "Test caveats."
        mock_ananta.get_analysis.assert_called_once_with("owner-myrepo")

    def test_get_analysis_no_analysis_exists(
        self, client: TestClient, mock_ananta: MagicMock
    ) -> None:
        """GET /api/repos/{id}/analysis returns 404 when no analysis exists."""
        mock_ananta.get_analysis.return_value = None

        resp = client.get("/api/repos/owner-myrepo/analysis")
        assert resp.status_code == 404

    def test_get_analysis_project_not_found(
        self, client: TestClient, mock_ananta: MagicMock
    ) -> None:
        """GET /api/repos/{id}/analysis returns 404 for missing project."""
        mock_ananta.get_analysis.side_effect = ProjectNotFoundError("nonexistent")

        resp = client.get("/api/repos/nonexistent/analysis")
        assert resp.status_code == 404
