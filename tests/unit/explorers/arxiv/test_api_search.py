"""Tests for search REST endpoints."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ananta.explorers.arxiv.papers.models import PaperMeta
from ananta.explorers.arxiv.api import create_api


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


def _make_meta(arxiv_id: str = "2501.08753", title: str = "Test Paper") -> MagicMock:
    meta = MagicMock(spec=PaperMeta)
    meta.arxiv_id = arxiv_id
    meta.title = title
    meta.authors = ["Author A"]
    meta.abstract = "Abstract text"
    meta.primary_category = "q-bio.PE"
    meta.published = datetime(2025, 1, 15)
    meta.arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
    meta.source_type = "latex"
    return meta


def test_search_arxiv(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.searcher.search.return_value = [_make_meta()]
    mock_state.topic_mgr.list_topics.return_value = []

    resp = client.get("/api/search?q=abiogenesis")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["arxiv_id"] == "2501.08753"
    assert data[0]["in_topics"] == []


def test_search_arxiv_with_filters(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.searcher.search.return_value = []
    mock_state.topic_mgr.list_topics.return_value = []

    resp = client.get("/api/search?q=test&author=Smith&category=cs.AI&sort_by=date&start=10")
    assert resp.status_code == 200
    call_kwargs = mock_state.searcher.search.call_args[1]
    assert call_kwargs["author"] == "Smith"
    assert call_kwargs["category"] == "cs.AI"
    assert call_kwargs["sort_by"] == "date"
    assert call_kwargs["start"] == 10


def test_search_arxiv_marks_existing_papers(client: TestClient, mock_state: MagicMock) -> None:
    from ananta.explorers.arxiv.papers.models import TopicInfo

    mock_state.searcher.search.return_value = [_make_meta("2501.08753")]
    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Abiogenesis",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-abio",
        ),
    ]
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.08753"]

    resp = client.get("/api/search?q=test")
    assert resp.status_code == 200
    data = resp.json()
    assert "Abiogenesis" in data[0]["in_topics"]


def test_search_local(client: TestClient, mock_state: MagicMock) -> None:
    from ananta.explorers.arxiv.papers.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Chess",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-chess",
        ),
    ]
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.12345"]
    meta = _make_meta("2501.12345", "Chess Strategies")
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/papers/search?q=chess")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["arxiv_id"] == "2501.12345"


def test_search_local_matches_author(client: TestClient, mock_state: MagicMock) -> None:
    from ananta.explorers.arxiv.papers.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Chess",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-chess",
        ),
    ]
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.12345"]
    meta = _make_meta("2501.12345", "Unrelated Title")
    meta.authors = ["Author A"]
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/papers/search?q=Author")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_search_local_matches_arxiv_id(client: TestClient, mock_state: MagicMock) -> None:
    from ananta.explorers.arxiv.papers.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Chess",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-chess",
        ),
    ]
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.12345"]
    meta = _make_meta("2501.12345", "Unrelated")
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/papers/search?q=2501.12345")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_search_local_reports_all_topics(client: TestClient, mock_state: MagicMock) -> None:
    """A paper in multiple topics should list all of them in in_topics."""
    from ananta.explorers.arxiv.papers.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Chess",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-chess",
        ),
        TopicInfo(
            name="AI",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-ai",
        ),
        TopicInfo(
            name="Games",
            created=datetime(2025, 1, 15),
            paper_count=1,
            size_bytes=1000,
            project_id="proj-games",
        ),
    ]
    # Same paper in all three topics
    mock_state.topic_mgr.storage.list_documents.return_value = ["2501.12345"]
    meta = _make_meta("2501.12345", "Chess AI Paper")
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/papers/search?q=chess")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert sorted(data[0]["in_topics"]) == ["AI", "Chess", "Games"]


def test_search_arxiv_returns_502_on_upstream_error(
    client: TestClient, mock_state: MagicMock
) -> None:
    """arxiv API errors should return 502, not crash with 500."""
    import arxiv

    mock_state.searcher.search.side_effect = arxiv.HTTPError(
        "https://export.arxiv.org/api/query?...", 3, 500
    )

    resp = client.get("/api/search?q=test")
    assert resp.status_code == 502
    assert "arXiv API" in resp.json()["detail"]
