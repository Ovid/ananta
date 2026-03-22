"""Tests for topical relevance checker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ananta.explorers.arxiv.papers.models import (
    ExtractedCitation,
    VerificationStatus,
)


class TestTopicalRelevanceChecker:
    """Tests for LLM-based topical relevance checking."""

    def test_flags_unrelated_citation(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="RNA Catalysis", authors=[], year=None),
            ExtractedCitation(key="b", title="Victorian Novel Analysis", authors=[], year=None),
        ]
        verified_keys = {"a", "b"}

        llm_response = json.dumps(
            [
                {
                    "key": "a",
                    "relevant": True,
                    "reason": "Directly related to RNA research",
                },
                {
                    "key": "b",
                    "relevant": False,
                    "reason": "Literary analysis unrelated to biochemistry",
                },
            ]
        )
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = llm_response

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            return_value=mock_completion,
        ):
            results = check_topical_relevance(
                paper_title="Abiogenesis and Early RNA World",
                paper_abstract="Study of early RNA...",
                citations=citations,
                verified_keys=verified_keys,
                model="test-model",
            )

        assert len(results) == 1
        assert results[0].citation_key == "b"
        assert results[0].status == VerificationStatus.TOPICALLY_UNRELATED

    def test_skips_unverified_citations(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
            ExtractedCitation(key="b", title="Paper B", authors=[], year=None),
        ]
        verified_keys = {"a"}

        llm_response = json.dumps(
            [
                {"key": "a", "relevant": True, "reason": "Related"},
            ]
        )
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = llm_response

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            return_value=mock_completion,
        ) as mock_llm:
            results = check_topical_relevance(
                paper_title="Test Paper",
                paper_abstract="Abstract...",
                citations=citations,
                verified_keys=verified_keys,
                model="test-model",
            )

        call_args = mock_llm.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"]
        assert "Paper B" not in prompt_text
        assert results == []

    def test_no_verified_citations_returns_empty(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        with patch("ananta.explorers.arxiv.papers.relevance.litellm.completion") as mock_llm:
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys=set(),
                model="test-model",
            )

        mock_llm.assert_not_called()
        assert results == []

    def test_llm_error_returns_empty(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            side_effect=Exception("API error"),
        ):
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
            )

        assert results == []

    def test_passes_api_key_to_litellm(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps(
            [{"key": "a", "relevant": True, "reason": "Related"}]
        )

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            return_value=mock_completion,
        ) as mock_llm:
            check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
                api_key="sk-test-key-123",
            )

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-key-123"

    def test_omits_api_key_when_none(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps(
            [{"key": "a", "relevant": True, "reason": "Related"}]
        )

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            return_value=mock_completion,
        ) as mock_llm:
            check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
            )

        call_kwargs = mock_llm.call_args.kwargs
        assert "api_key" not in call_kwargs

    def test_malformed_json_returns_empty(self) -> None:
        from ananta.explorers.arxiv.papers.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "not valid json"

        with patch(
            "ananta.explorers.arxiv.papers.relevance.litellm.completion",
            return_value=mock_completion,
        ):
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
            )

        assert results == []
