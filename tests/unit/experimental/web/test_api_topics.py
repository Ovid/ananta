"""Tests for topics REST endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.download_tasks = {}
    return state


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = create_api(mock_state)
    return TestClient(app)


def test_list_topics_empty(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.list_topics.return_value = []
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_topics(client: TestClient, mock_state: MagicMock) -> None:
    from datetime import datetime

    from shesha.experimental.arxiv.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Abiogenesis",
            created=datetime(2025, 1, 15),
            paper_count=5,
            size_bytes=1024000,
            project_id="2025-01-15-abiogenesis",
        ),
    ]
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Abiogenesis"
    assert data[0]["document_count"] == 5


def test_create_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    mock_state.topic_mgr.create.return_value = "2025-01-15-chess"
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 201
    mock_state.topic_mgr.create.assert_called_once_with("Chess")


def test_create_topic_already_exists(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "existing-id"
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 409


def test_rename_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 200
    mock_state.topic_mgr.rename.assert_called_once()


def test_rename_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.rename.side_effect = ValueError("not found")
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 404


def test_delete_topic(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.delete("/api/topics/chess")
    assert resp.status_code == 200
    mock_state.topic_mgr.delete.assert_called_once()


def test_delete_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.delete.side_effect = ValueError("not found")
    resp = client.delete("/api/topics/nonexistent")
    assert resp.status_code == 404
