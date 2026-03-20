"""Tests for arXiv search wrapper."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from threading import RLock
from unittest.mock import MagicMock, patch

import pytest


def _mock_arxiv_result(
    arxiv_id: str = "2501.12345",
    title: str = "Test Paper",
    authors: list[str] | None = None,
) -> MagicMock:
    """Create a mock arxiv.Result object."""
    result = MagicMock()
    result.entry_id = f"http://arxiv.org/abs/{arxiv_id}"
    result.title = title
    result.summary = "An abstract."
    result.published = datetime(2025, 1, 15, tzinfo=UTC)
    result.updated = datetime(2025, 1, 15, tzinfo=UTC)
    result.categories = ["cs.AI"]
    result.primary_category = "cs.AI"
    result.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    result.comment = "10 pages"
    result.journal_ref = None
    result.doi = None
    # Authors are objects with .name attribute
    author_names = authors or ["Smith, J.", "Doe, A."]
    result.authors = [MagicMock(name=n) for n in author_names]
    # Fix: MagicMock(name=...) sets the mock's name, not .name attribute
    for author, name in zip(result.authors, author_names):
        author.name = name
    return result


class TestArxivSearcher:
    """Tests for ArxivSearcher."""

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_returns_paper_metas(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        results = searcher.search("quantum computing")
        assert len(results) == 1
        assert results[0].arxiv_id == "2501.12345"
        assert results[0].title == "Test Paper"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_category(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("language models", category="cs.AI")
        # Verify the query included the category
        search_call = mock_arxiv.Search.call_args
        assert "cat:cs.AI" in search_call.kwargs.get(
            "query", search_call.args[0] if search_call.args else ""
        )

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_by_author(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("", author="del maestro")
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "au:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_start_offset(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        searcher.search("quantum", start=10)
        # offset is passed to client.results(), not Search()
        results_call = mock_client.results.call_args
        assert results_call.kwargs.get("offset") == 10
        # max_results includes offset so enough results are fetched
        search_call = mock_arxiv.Search.call_args
        assert search_call.kwargs.get("max_results") == 20

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_recent_days(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("quantum", recent_days=7)
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "submittedDate:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("2501.12345")
        assert meta is not None
        assert meta.arxiv_id == "2501.12345"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id_not_found(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("0000.00000")
        assert meta is None

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id_http_error_returns_none(self, mock_arxiv: MagicMock) -> None:
        """Invalid IDs that cause HTTP errors should return None, not crash."""
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.side_effect = Exception("HTTP 400")

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("https://example.com/not-an-arxiv-id")
        assert meta is None

    def test_format_result(self) -> None:
        # Late import: module under test
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.experimental.arxiv.search import format_result

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Topological Quantum Error Correction with Low Overhead",
            authors=["Smith, J.", "Jones, K.", "Lee, M."],
            abstract="Abstract",
            published=datetime(2025, 1, 15, tzinfo=UTC),
            updated=datetime(2025, 1, 15, tzinfo=UTC),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            comment="12 pages",
        )
        output = format_result(meta, index=1)
        assert "[2501.12345]" in output
        assert "Topological Quantum Error Correction" in output
        assert "Smith, J." in output
        assert "cs.QI" in output
        assert "https://arxiv.org/abs/2501.12345" in output

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_sort_by_date(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("quantum", sort_by="date")
        search_call = mock_arxiv.Search.call_args
        assert search_call.kwargs.get("sort_by") == mock_arxiv.SortCriterion.SubmittedDate

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_sort_by_defaults_to_relevance(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("quantum")
        search_call = mock_arxiv.Search.call_args
        assert search_call.kwargs.get("sort_by") == mock_arxiv.SortCriterion.Relevance

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_wildcard_query_with_author_omits_all_prefix(
        self, mock_arxiv: MagicMock
    ) -> None:
        """query='*' with author should produce 'au:X', not 'all:* AND au:X'."""
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("*", author="Nicolas Gisin")
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "all:*" not in query
        assert "au:Nicolas Gisin" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_wildcard_query_alone_raises(self, mock_arxiv: MagicMock) -> None:
        """query='*' with no other filters should raise ValueError."""
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client

        searcher = ArxivSearcher()
        with pytest.raises(ValueError, match="search criteria"):
            searcher.search("*")

    def test_extract_arxiv_id_from_entry_id(self) -> None:
        # Late import: module under test
        from shesha.experimental.arxiv.search import extract_arxiv_id

        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345v1") == "2501.12345v1"
        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345") == "2501.12345"

    def test_extract_arxiv_id_replaces_slash_in_old_style_ids(self) -> None:
        """Old-style arXiv IDs like cs/9808001v1 must have / replaced with -.

        Slashes in IDs break _SAFE_ID_RE validation and create subdirectories
        in the storage layer.
        """
        from shesha.experimental.arxiv.search import extract_arxiv_id

        assert extract_arxiv_id("http://arxiv.org/abs/cs/9808001v1") == "cs-9808001v1"
        assert extract_arxiv_id("http://arxiv.org/abs/astro-ph/0601001v1") == "astro-ph-0601001v1"
        assert extract_arxiv_id("http://arxiv.org/abs/math/0703001") == "math-0703001"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_old_style_id_preserves_slash_in_urls(self, mock_arxiv: MagicMock) -> None:
        """Old-style IDs get sanitized for arxiv_id but URLs keep the slash."""
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter(
            [_mock_arxiv_result(arxiv_id="cs/9808001v1")]
        )

        searcher = ArxivSearcher()
        results = searcher.search("chess")
        assert results[0].arxiv_id == "cs-9808001v1"
        assert results[0].arxiv_url == "https://arxiv.org/abs/cs/9808001v1"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_close_closes_underlying_session(self, mock_arxiv: MagicMock) -> None:
        """close() should close the arxiv.Client's requests session."""
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_pool = MagicMock()
        mock_pools_container = MagicMock()
        mock_pools_container.lock = RLock()
        mock_pools_container._container = OrderedDict({"key": mock_pool})
        mock_adapter = MagicMock()
        mock_adapter.poolmanager.pools = mock_pools_container

        mock_client = MagicMock()
        mock_client._session.adapters.values.return_value = [mock_adapter]
        mock_arxiv.Client.return_value = mock_client

        searcher = ArxivSearcher()
        searcher.close()
        mock_pool.close.assert_called_once()
        mock_client._session.close.assert_called_once()
