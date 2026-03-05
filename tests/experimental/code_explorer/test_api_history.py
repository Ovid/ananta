"""Tests for per-topic conversation history in code explorer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.session import WebConversationSession


@pytest.fixture()
def state(tmp_path: Path) -> CodeExplorerState:
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha._storage = MagicMock()
    shesha._storage.list_traces.return_value = []

    topics_dir = tmp_path / "topics"
    topics_dir.mkdir()
    topic_mgr = CodeExplorerTopicManager(topics_dir)
    topic_mgr.create("Alpha")
    topic_mgr.create("Beta")

    session = WebConversationSession(tmp_path)
    return CodeExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model="test-model",
    )


@pytest.fixture()
def client(state: CodeExplorerState) -> TestClient:
    app = create_api(state)
    return TestClient(app)


class TestPerTopicHistory:
    def test_topics_have_independent_history(
        self, client: TestClient, state: CodeExplorerState
    ) -> None:
        """Each topic should have its own conversation history."""
        resp_a = client.get("/api/topics/Alpha/history")
        assert resp_a.status_code == 200
        assert resp_a.json()["exchanges"] == []

        resp_b = client.get("/api/topics/Beta/history")
        assert resp_b.status_code == 200
        assert resp_b.json()["exchanges"] == []

    def test_clear_only_affects_target_topic(
        self, client: TestClient, state: CodeExplorerState
    ) -> None:
        """Clearing one topic's history should not affect another."""
        from shesha.experimental.code_explorer.dependencies import get_topic_session

        alpha_session = get_topic_session(state, "Alpha")
        alpha_session.add_exchange(
            question="Q1",
            answer="A1",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        beta_session = get_topic_session(state, "Beta")
        beta_session.add_exchange(
            question="Q2",
            answer="A2",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        # Clear Alpha
        resp = client.delete("/api/topics/Alpha/history")
        assert resp.status_code == 200

        # Alpha should be empty
        resp_a = client.get("/api/topics/Alpha/history")
        assert resp_a.json()["exchanges"] == []

        # Beta should still have its exchange
        resp_b = client.get("/api/topics/Beta/history")
        assert len(resp_b.json()["exchanges"]) == 1

    def test_global_history_routes_removed(self, client: TestClient) -> None:
        """The old global /api/history endpoint should no longer exist."""
        resp = client.get("/api/history")
        assert resp.status_code == 404

        resp = client.delete("/api/history")
        # 404 when no SPA catch-all, 405 when the SPA static mount
        # intercepts the path but rejects non-GET methods.
        assert resp.status_code in (404, 405)
