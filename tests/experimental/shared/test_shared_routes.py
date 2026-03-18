"""Tests for shared router callback parameters."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shesha.experimental.shared.routes import create_shared_router
from shesha.experimental.shared.schemas import TopicInfo
from shesha.experimental.shared.session import WebConversationSession


def _make_state(tmp_path: Path) -> MagicMock:
    """Build a minimal mock state for the shared router."""
    state = MagicMock()
    state.model = "test-model"
    state.topic_mgr.list_topics.return_value = []
    state.topic_mgr.resolve.return_value = None
    state.topic_mgr._storage.list_traces.return_value = []
    return state


def _make_app(state: MagicMock, **kwargs: object) -> FastAPI:
    app = FastAPI()
    router = create_shared_router(state, **kwargs)
    app.include_router(router)
    return app


class TestBuildTopicInfoCallback:
    """The build_topic_info callback overrides topic listing."""

    def test_default_uses_topic_mgr(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        topic = MagicMock()
        topic.name = "my-topic"
        topic.document_count = 3
        topic.formatted_size = "1.2 MB"
        topic.project_id = "proj-1"
        state.topic_mgr.list_topics.return_value = [topic]

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-topic"
        assert data[0]["document_count"] == 3

    def test_custom_callback_overrides_listing(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)

        def custom_topics(s: object) -> list[TopicInfo]:
            return [TopicInfo(name="custom", document_count=7, size="2 MB", project_id="p1")]

        app = _make_app(state, build_topic_info=custom_topics)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "custom"
        assert data[0]["document_count"] == 7


class TestGetSessionCallback:
    """The get_session callback controls which session is used for history."""

    def test_default_uses_per_project_session(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        project_dir = tmp_path / "proj-1"
        project_dir.mkdir()
        state.topic_mgr._storage._project_path.return_value = project_dir

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/history")
        assert resp.status_code == 200
        assert resp.json()["exchanges"] == []

    def test_custom_session_callback(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"

        # Create a global session with an exchange
        global_session = WebConversationSession(tmp_path)
        global_session.add_exchange(
            question="hi",
            answer="hello",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def custom_session(s: object, topic_name: str) -> WebConversationSession:
            return global_session

        app = _make_app(state, get_session=custom_session)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/history")
        assert resp.status_code == 200
        assert len(resp.json()["exchanges"]) == 1
        assert resp.json()["exchanges"][0]["question"] == "hi"

    def test_custom_session_used_for_export(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"

        # Create a session with an exchange
        session = WebConversationSession(tmp_path)
        session.add_exchange(
            question="export me",
            answer="exported answer",
            trace_id=None,
            tokens={"prompt": 5, "completion": 10, "total": 15},
            execution_time=0.5,
            model="test",
        )

        def custom_session(s: object, topic_name: str) -> WebConversationSession:
            return session

        app = _make_app(state, get_session=custom_session)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
        body = resp.text
        assert "export me" in body
        assert "exported answer" in body

    def test_custom_session_used_for_context_budget(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        state.model = "test-model"

        # Create a session with an exchange so context_chars() > 0
        session = WebConversationSession(tmp_path)
        session.add_exchange(
            question="budget question",
            answer="budget answer",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def custom_session(s: object, topic_name: str) -> WebConversationSession:
            return session

        app = _make_app(state, get_session=custom_session)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/context-budget")
        assert resp.status_code == 200
        data = resp.json()
        # The session has "budget question" (15 chars) + "budget answer" (13 chars)
        # = 28 chars -> 28 // 4 = 7 tokens from history + 2000 base = 2007
        expected_history_tokens = len("budget question") + len("budget answer")
        expected_used = 2000 + (expected_history_tokens // 4)
        assert data["used_tokens"] == expected_used
        assert data["max_tokens"] > 0
        assert data["level"] == "green"
        assert data["percentage"] > 0


class TestResolveProjectIdsCallback:
    """The resolve_project_ids callback controls trace aggregation."""

    def test_default_uses_resolve_all(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve_all = MagicMock(return_value=["p1", "p2"])
        state.topic_mgr._storage.list_traces.return_value = []

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        state.topic_mgr.resolve_all.assert_called_once_with("my-topic")

    def test_custom_callback_overrides_resolution(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = []

        def custom_resolve(s: object, name: str) -> list[str]:
            return ["custom-proj"]

        app = _make_app(state, resolve_project_ids=custom_resolve)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        state.topic_mgr._storage.list_traces.assert_called_once_with("custom-proj")


class TestListTraceFilesCallback:
    """The list_trace_files callback controls trace file retrieval."""

    def test_default_uses_topic_mgr_storage(self, tmp_path: Path) -> None:
        """Default behavior accesses state.topic_mgr._storage.list_traces()."""
        state = _make_state(tmp_path)
        state.topic_mgr.resolve_all = MagicMock(return_value=["p1"])
        state.topic_mgr._storage.list_traces.return_value = []

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        state.topic_mgr._storage.list_traces.assert_called_once_with("p1")

    def test_custom_callback_overrides_trace_retrieval(self, tmp_path: Path) -> None:
        """Custom list_trace_files callback bypasses topic_mgr._storage."""
        state = _make_state(tmp_path)
        custom_storage = MagicMock()
        custom_storage.list_traces.return_value = []

        def custom_list_traces(s: object, project_id: str) -> list[Path]:
            return custom_storage.list_traces(project_id)

        def custom_resolve(s: object, name: str) -> list[str]:
            return ["my-proj"]

        app = _make_app(
            state,
            resolve_project_ids=custom_resolve,
            list_trace_files=custom_list_traces,
        )
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        custom_storage.list_traces.assert_called_once_with("my-proj")
        # The default state.topic_mgr._storage should NOT be called
        state.topic_mgr._storage.list_traces.assert_not_called()


class TestIncludeTopicCrud:
    """The include_topic_crud flag controls topic CRUD route registration."""

    def test_topic_crud_included_by_default(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200

    def test_topic_crud_excluded(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(state, include_topic_crud=False)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code in (404, 405)


class TestCodeExplorerCallbacks:
    """Code explorer uses global session and custom topic listing."""

    def test_global_session_used_for_history(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"

        global_session = WebConversationSession(tmp_path)
        global_session.add_exchange(
            question="global q",
            answer="global a",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def get_global_session(s: object, topic_name: str) -> WebConversationSession:
            return global_session

        app = _make_app(state, get_session=get_global_session)
        client = TestClient(app)
        resp = client.get("/api/topics/any-topic/history")
        assert resp.status_code == 200
        assert len(resp.json()["exchanges"]) == 1
        assert resp.json()["exchanges"][0]["question"] == "global q"

    def test_custom_topic_listing(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)

        def build_code_topics(s: object) -> list[TopicInfo]:
            return [
                TopicInfo(
                    name="my-topic",
                    document_count=2,
                    size="",
                    project_id="topic:my-topic",
                )
            ]

        app = _make_app(state, build_topic_info=build_code_topics)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["document_count"] == 2
        assert data[0]["project_id"] == "topic:my-topic"


class TestTraceDownload:
    """The trace-download endpoint returns the raw JSONL file."""

    def _make_trace_file(
        self,
        tmp_path: Path,
        filename: str = "2025-01-15T10-30-00-123_abc12345.jsonl",
    ) -> Path:
        trace_file = tmp_path / filename
        header = {
            "type": "header",
            "trace_id": "abc12345",
            "timestamp": "2025-01-15T10:30:00Z",
            "question": "What is abiogenesis?",
            "document_ids": ["doc1"],
            "model": "gpt-5-mini",
            "system_prompt": "You are a helpful assistant",
            "subcall_prompt": "Answer concisely",
        }
        step = {
            "type": "step",
            "step_type": "code_generated",
            "iteration": 0,
            "timestamp": "2025-01-15T10:30:01Z",
            "content": "print('hello')",
            "tokens_used": 150,
            "duration_ms": None,
        }
        summary = {
            "type": "summary",
            "answer": "Abiogenesis is...",
            "total_iterations": 1,
            "total_tokens": {"prompt": 100, "completion": 50},
            "total_duration_ms": 5000,
            "status": "success",
        }
        trace_file.write_text(
            json.dumps(header)
            + "\n"
            + json.dumps(step)
            + "\n"
            + json.dumps(summary)
            + "\n"
        )
        return trace_file

    def test_download_returns_raw_jsonl(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        state.topic_mgr.resolve_all = MagicMock(return_value=["proj-1"])
        trace_file = self._make_trace_file(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = [trace_file]

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/abc12345")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-ndjson"
        assert "attachment" in resp.headers["content-disposition"]
        assert (
            "2025-01-15T10-30-00-123_abc12345.jsonl"
            in resp.headers["content-disposition"]
        )
        # Body is the raw file content
        lines = resp.text.strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["type"] == "header"
        assert json.loads(lines[0])["system_prompt"] == "You are a helpful assistant"

    def test_download_matches_by_stem(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        state.topic_mgr.resolve_all = MagicMock(return_value=["proj-1"])
        trace_file = self._make_trace_file(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = [trace_file]

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get(
            "/api/topics/my-topic/trace-download/2025-01-15T10-30-00-123_abc12345"
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]

    def test_download_not_found(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        state.topic_mgr.resolve_all = MagicMock(return_value=["proj-1"])
        state.topic_mgr._storage.list_traces.return_value = []

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/nonexistent")
        assert resp.status_code == 404

    def test_download_uses_custom_callbacks(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        trace_file = self._make_trace_file(tmp_path)

        def custom_resolve(s: object, name: str) -> list[str]:
            return ["custom-proj"]

        def custom_list(s: object, project_id: str) -> list[Path]:
            return [trace_file]

        app = _make_app(
            state,
            resolve_project_ids=custom_resolve,
            list_trace_files=custom_list,
        )
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/abc12345")
        assert resp.status_code == 200
