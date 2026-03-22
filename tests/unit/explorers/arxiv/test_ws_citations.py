"""Tests for WebSocket citation check handler."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ananta.explorers.arxiv.api import create_api
from ananta.explorers.arxiv.papers.models import (
    VerificationResult,
    VerificationStatus,
)


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


class TestCheckCitationsHandler:
    """Tests for the check_citations WebSocket message handler."""

    def test_requires_topic(self, client: TestClient, mock_state: MagicMock) -> None:
        """Returns error when topic not found."""
        mock_state.topic_mgr.resolve.return_value = None
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "check_citations", "topic": "nope", "paper_ids": ["p1"]})
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["message"]

    def test_requires_paper_ids(self, client: TestClient, mock_state: MagicMock) -> None:
        """Returns error when no paper_ids provided."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "check_citations", "topic": "test"})
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "paper" in msg["message"].lower()

    def test_sends_progress_and_report(self, client: TestClient, mock_state: MagicMock) -> None:
        """Sends citation_progress messages then citation_report for each paper."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"

        # Set up cache to return metadata and source files
        meta = MagicMock()
        meta.arxiv_id = "2301.00001"
        meta.title = "Test Paper"
        mock_state.cache.get_meta.return_value = meta
        mock_state.cache.get_source_files.return_value = {
            "refs.bib": "@article{key1, title={Some Paper}, eprint={2301.99999}}"
        }

        # Mock the verifier to avoid real arXiv calls
        mock_result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED,
            arxiv_url="https://arxiv.org/abs/2301.99999",
        )
        with patch("ananta.explorers.arxiv.websockets.ArxivVerifier") as mock_verifier_cls:
            mock_verifier = MagicMock()
            mock_verifier.verify.return_value = mock_result
            mock_verifier_cls.return_value = mock_verifier

            with client.websocket_connect("/api/ws") as ws:
                ws.send_json(
                    {
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["2301.00001"],
                    }
                )
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("citation_report", "error"):
                        break

        types = [m["type"] for m in messages]
        assert "citation_progress" in types
        assert "citation_report" in types

        progress_msgs = [m for m in messages if m["type"] == "citation_progress"]
        assert progress_msgs[0]["current"] == 1
        assert progress_msgs[0]["total"] == 1

        report_msg = [m for m in messages if m["type"] == "citation_report"][0]
        assert "papers" in report_msg
        papers = report_msg["papers"]
        assert isinstance(papers, list)
        assert len(papers) == 1
        paper = papers[0]
        assert paper["arxiv_id"] == "2301.00001"
        assert paper["title"] == "Test Paper"
        assert "group" in paper
        assert "mismatches" in paper
        assert "llm_phrases" in paper

    def test_skips_papers_without_metadata(self, client: TestClient, mock_state: MagicMock) -> None:
        """Papers without cached metadata are skipped."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"
        mock_state.cache.get_meta.return_value = None
        mock_state.cache.get_source_files.return_value = None

        with patch("ananta.explorers.arxiv.websockets.ArxivVerifier"):
            with client.websocket_connect("/api/ws") as ws:
                ws.send_json(
                    {
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["unknown-paper"],
                    }
                )
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("citation_report", "error"):
                        break

        # Should still get a report with empty papers list, not an error
        report_msgs = [m for m in messages if m["type"] == "citation_report"]
        assert len(report_msgs) == 1
        assert report_msgs[0]["papers"] == []

    def test_sends_per_citation_progress(self, client: TestClient, mock_state: MagicMock) -> None:
        """Progress messages include citation-level detail in phase field."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"

        meta = MagicMock()
        meta.arxiv_id = "2301.00001"
        meta.title = "Test Paper"
        mock_state.cache.get_meta.return_value = meta
        mock_state.cache.get_source_files.return_value = {
            "refs.bib": (
                "@article{a, title={Paper A}, eprint={2301.11111}}\n"
                "@article{b, title={Paper B}, eprint={2301.22222}}\n"
                "@article{c, title={Paper C}, eprint={2301.33333}}"
            )
        }

        mock_result = VerificationResult(
            citation_key="a",
            status=VerificationStatus.VERIFIED,
            arxiv_url="https://arxiv.org/abs/2301.11111",
        )
        with patch("ananta.explorers.arxiv.websockets.ArxivVerifier") as mock_verifier_cls:
            mock_verifier = MagicMock()
            mock_verifier.verify.return_value = mock_result
            mock_verifier_cls.return_value = mock_verifier

            with client.websocket_connect("/api/ws") as ws:
                ws.send_json(
                    {
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["2301.00001"],
                    }
                )
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("citation_report", "error"):
                        break

        progress_msgs = [m for m in messages if m["type"] == "citation_progress"]
        # Should have at least one progress with citation-level phase info
        phases = [m.get("phase", "") for m in progress_msgs]
        assert any("/" in p and "citation" in p.lower() for p in phases), (
            f"Expected citation-level progress in phases, got: {phases}"
        )

    def test_falls_back_to_text_extraction(self, client: TestClient, mock_state: MagicMock) -> None:
        """When no source files, falls back to extracting arXiv IDs from document text."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"

        meta = MagicMock()
        meta.arxiv_id = "2301.00001"
        meta.title = "Test Paper"
        mock_state.cache.get_meta.return_value = meta
        mock_state.cache.get_source_files.return_value = None

        # Storage returns document with arXiv ID in content
        doc = MagicMock()
        doc.content = "This paper cites arXiv:2301.55555 in the text."
        mock_state.topic_mgr.storage.get_document.return_value = doc

        mock_result = VerificationResult(
            citation_key="text-2301.55555",
            status=VerificationStatus.VERIFIED,
        )
        with patch("ananta.explorers.arxiv.websockets.ArxivVerifier") as mock_verifier_cls:
            mock_verifier = MagicMock()
            mock_verifier.verify.return_value = mock_result
            mock_verifier_cls.return_value = mock_verifier

            with client.websocket_connect("/api/ws") as ws:
                ws.send_json(
                    {
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["2301.00001"],
                    }
                )
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("citation_report", "error"):
                        break

        # Verifier should have been called
        mock_verifier.verify.assert_called_once()
