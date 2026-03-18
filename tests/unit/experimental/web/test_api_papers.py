"""Tests for papers REST endpoints."""

from unittest.mock import MagicMock, patch

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


def test_list_papers_in_topic(client: TestClient, mock_state: MagicMock) -> None:
    from datetime import datetime

    from shesha.experimental.arxiv.models import PaperMeta

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.08753"]

    meta = MagicMock(spec=PaperMeta)
    meta.arxiv_id = "2501.08753"
    meta.title = "Test Paper"
    meta.authors = ["Author A"]
    meta.abstract = "Abstract"
    meta.primary_category = "q-bio.PE"
    meta.published = datetime(2025, 1, 15)
    meta.arxiv_url = "https://arxiv.org/abs/2501.08753"
    meta.source_type = "latex"
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/topics/test-topic/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["arxiv_id"] == "2501.08753"
    assert data[0]["title"] == "Test Paper"


def test_list_papers_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    resp = client.get("/api/topics/nonexistent/papers")
    assert resp.status_code == 404


def test_add_paper_cached(client: TestClient, mock_state: MagicMock) -> None:
    """Paper already in cache copies immediately, returns 200."""
    mock_state.cache.has.return_value = True
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    mock_doc = MagicMock()
    with patch("shesha.experimental.web.api.to_parsed_document", return_value=mock_doc):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "2501.08753", "topics": ["Chess"]},
        )

    assert resp.status_code == 200
    mock_state.topic_mgr.storage.store_document.assert_called_once()


def test_add_paper_needs_download(client: TestClient, mock_state: MagicMock) -> None:
    """Paper not cached returns 202 with task_id."""
    mock_state.cache.has.return_value = False
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    resp = client.post(
        "/api/papers/add",
        json={"arxiv_id": "2501.08753", "topics": ["Chess"]},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data


def test_add_paper_multi_topic_cached(client: TestClient, mock_state: MagicMock) -> None:
    """Cached paper added to multiple topics."""
    mock_state.cache.has.return_value = True
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    mock_doc = MagicMock()
    with patch("shesha.experimental.web.api.to_parsed_document", return_value=mock_doc):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "2501.08753", "topics": ["Chess", "Education"]},
        )

    assert resp.status_code == 200
    assert mock_state.topic_mgr.storage.store_document.call_count == 2


def test_remove_paper(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client.delete("/api/topics/chess/papers/2501.08753")
    assert resp.status_code == 200
    mock_state.topic_mgr.storage.delete_document.assert_called_once_with("proj-id", "2501.08753")


def test_remove_paper_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    resp = client.delete("/api/topics/nonexistent/papers/2501.08753")
    assert resp.status_code == 404


def test_download_task_status(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.download_tasks = {
        "task-123": {
            "papers": [{"arxiv_id": "2501.08753", "status": "downloading"}],
        }
    }
    resp = client.get("/api/papers/tasks/task-123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-123"


def test_download_task_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.download_tasks = {}
    resp = client.get("/api/papers/tasks/nonexistent")
    assert resp.status_code == 404


def test_add_paper_download_fetches_meta_from_searcher(
    client: TestClient, mock_state: MagicMock
) -> None:
    """Background download should fetch metadata via searcher, not cache.

    When cache.has() is False, cache.get_meta() also returns None (both check
    meta.json existence). The download thread must use searcher.get_by_id()
    to obtain metadata before calling download_paper().
    """
    import threading
    from datetime import datetime

    from shesha.experimental.arxiv.models import PaperMeta

    mock_state.cache.has.return_value = False
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    meta = PaperMeta(
        arxiv_id="2501.08753",
        title="Test Paper",
        authors=["Author A"],
        abstract="Abstract",
        published=datetime(2025, 1, 15),
        updated=datetime(2025, 1, 15),
        categories=["q-bio.PE"],
        primary_category="q-bio.PE",
        pdf_url="https://arxiv.org/pdf/2501.08753",
        arxiv_url="https://arxiv.org/abs/2501.08753",
    )
    mock_state.searcher.get_by_id.return_value = meta

    mock_doc = MagicMock()

    # Capture the thread so we can wait for it
    original_thread_init = threading.Thread.__init__
    thread_ref: list[threading.Thread] = []

    def capture_thread(self: threading.Thread, *args: object, **kwargs: object) -> None:
        original_thread_init(self, *args, **kwargs)  # type: ignore[arg-type]
        thread_ref.append(self)

    with (
        patch.object(threading.Thread, "__init__", capture_thread),
        patch(
            "shesha.experimental.arxiv.download.download_paper", return_value=meta
        ) as mock_download,
        patch("shesha.experimental.arxiv.download.to_parsed_document", return_value=mock_doc),
    ):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "2501.08753", "topics": ["Chess"]},
        )

        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        # Wait for the background thread to finish
        for t in thread_ref:
            t.join(timeout=5)

    # The download thread should have fetched meta from searcher, not cache
    mock_state.searcher.get_by_id.assert_called_once_with("2501.08753")
    mock_download.assert_called_once_with(meta, mock_state.cache)

    # Task should complete successfully
    assert mock_state.download_tasks[task_id]["papers"][0]["status"] == "complete"


def test_add_paper_download_errors_when_searcher_returns_none(
    client: TestClient, mock_state: MagicMock
) -> None:
    """If searcher can't find the paper, the task should report error."""
    import threading

    mock_state.cache.has.return_value = False
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"
    mock_state.searcher.get_by_id.return_value = None

    original_thread_init = threading.Thread.__init__
    thread_ref: list[threading.Thread] = []

    def capture_thread(self: threading.Thread, *args: object, **kwargs: object) -> None:
        original_thread_init(self, *args, **kwargs)  # type: ignore[arg-type]
        thread_ref.append(self)

    with patch.object(threading.Thread, "__init__", capture_thread):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "9999.99999", "topics": ["Chess"]},
        )

        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        for t in thread_ref:
            t.join(timeout=5)

    assert mock_state.download_tasks[task_id]["papers"][0]["status"] == "error"
