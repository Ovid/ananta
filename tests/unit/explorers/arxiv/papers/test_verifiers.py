"""Tests for external citation verifiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ananta.explorers.arxiv.papers.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)


class TestCrossRefVerifier:
    """Tests for CrossRef DOI and title verification."""

    def test_verify_by_doi_verified(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction",
            authors=[],
            year=None,
            doi="10.1234/example",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {
                "title": ["Quantum Error Correction"],
                "DOI": "10.1234/example",
            },
        }
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_by_doi_not_found(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="bad",
            title="Does Not Exist",
            authors=[],
            year=None,
            doi="10.9999/nonexistent",
        )
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.NOT_FOUND

    def test_verify_by_title_search(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="jones2023",
            title="Surface Codes Revisited",
            authors=[],
            year=None,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {"items": [{"title": ["Surface Codes Revisited"], "DOI": "10.5678/sc"}]},
        }
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_no_identifiers_no_title(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(key="anon", title=None, authors=[], year=None)
        verifier = CrossRefVerifier()
        result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_uses_polite_email_in_headers(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="x",
            title="T",
            authors=[],
            year=None,
            doi="10.1234/x",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {"title": ["T"], "DOI": "10.1234/x"},
        }
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ) as mock_get:
            verifier = CrossRefVerifier(polite_email="user@example.com")
            verifier.verify(citation)
        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        user_agent = headers.get("User-Agent", "")
        assert "mailto:user@example.com" in user_agent

    def test_verify_network_error_returns_unresolved(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CrossRefVerifier

        citation = ExtractedCitation(key="x", title="T", authors=[], year=None, doi="10.1234/x")
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            side_effect=Exception("timeout"),
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED


class TestOpenAlexVerifier:
    """Tests for OpenAlex title search verification."""

    def test_verify_title_match(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction",
            authors=[],
            year=None,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Quantum Error Correction",
                    "doi": "https://doi.org/10.1234/x",
                }
            ]
        }
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = OpenAlexVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "openalex"

    def test_verify_no_results(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(
            key="x", title="Nonexistent Paper Title", authors=[], year=None
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = OpenAlexVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_no_title_returns_unresolved(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(key="x", title=None, authors=[], year=None)
        verifier = OpenAlexVerifier()
        result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_polite_email_in_query_params(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(key="x", title="Test", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ) as mock_get:
            verifier = OpenAlexVerifier(polite_email="user@example.com")
            verifier.verify(citation)
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("mailto") == "user@example.com"


class TestSemanticScholarVerifier:
    """Tests for Semantic Scholar title search verification."""

    def test_verify_title_match(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(
            key="x", title="Quantum Error Correction", authors=[], year=None
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"title": "Quantum Error Correction", "paperId": "abc123"}]
        }
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "semantic_scholar"

    def test_verify_no_results(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(key="x", title="Nonexistent Paper", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_rate_limited_returns_unresolved(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(key="x", title="Test", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 429
        with patch(
            "ananta.explorers.arxiv.papers.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_respects_1_second_rate_limit(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import SemanticScholarVerifier

        verifier = SemanticScholarVerifier()
        assert verifier._limiter._min_interval >= 1.0


class TestCascadingVerifier:
    """Tests for the cascading verification orchestrator."""

    def test_arxiv_id_uses_arxiv_verifier_first(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="T", authors=[], year=None, arxiv_id="2301.00001"
        )

        mock_arxiv = MagicMock()
        mock_arxiv.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED, source="arxiv"
        )

        verifier = CascadingVerifier(arxiv_verifier=mock_arxiv)
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED
        mock_arxiv.verify.assert_called_once()

    def test_arxiv_not_found_falls_through_to_external(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Some Paper", authors=[], year=None, arxiv_id="2301.99999"
        )

        mock_arxiv = MagicMock()
        mock_arxiv.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.NOT_FOUND, severity="error"
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
        )

        verifier = CascadingVerifier(arxiv_verifier=mock_arxiv, openalex_verifier=mock_openalex)
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL

    def test_doi_uses_crossref_first(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="T", authors=[], year=None, doi="10.1234/example"
        )

        mock_crossref = MagicMock()
        mock_crossref.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="crossref"
        )

        verifier = CascadingVerifier(crossref_verifier=mock_crossref)
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_title_only_cascades_through_external_verifiers(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(key="x", title="Some Paper", authors=[], year=None)

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="semantic_scholar",
        )

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex, semantic_scholar_verifier=mock_s2
        )
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "semantic_scholar"

    def test_all_fail_returns_unresolved(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(key="x", title="Totally Unknown Paper", authors=[], year=None)

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_crossref = MagicMock()
        mock_crossref.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex,
            semantic_scholar_verifier=mock_s2,
            crossref_verifier=mock_crossref,
        )
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.UNRESOLVED

    def test_stops_at_first_verified(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(key="x", title="Found Paper", authors=[], year=None)

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
        )
        mock_s2 = MagicMock()

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex, semantic_scholar_verifier=mock_s2
        )
        verifier.verify(citation)

        mock_s2.verify.assert_not_called()

    def test_ambiguous_match_triggers_llm_judgment(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Learning Chess from Text", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.UNRESOLVED,
            source="openalex",
            actual_title="LEAP: Learning to Play Chess from Textbooks",
            message="Title match ambiguous (similarity=0.65)",
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "YES. These are the same paper."

        with patch(
            "ananta.explorers.arxiv.papers.verifiers.litellm.completion",
            return_value=mock_completion,
        ):
            verifier = CascadingVerifier(openalex_verifier=mock_openalex, model="test-model")
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert "LLM title judgment" in (result.message or "")

    def test_ambiguous_match_passes_api_key_to_llm(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Learning Chess from Text", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.UNRESOLVED,
            source="openalex",
            actual_title="LEAP: Learning to Play Chess from Textbooks",
            message="Title match ambiguous (similarity=0.65)",
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "YES. Same paper."

        with patch(
            "ananta.explorers.arxiv.papers.verifiers.litellm.completion",
            return_value=mock_completion,
        ) as mock_llm:
            verifier = CascadingVerifier(
                openalex_verifier=mock_openalex,
                model="test-model",
                api_key="sk-test-key-456",
            )
            verifier.verify(citation)

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-key-456"

    def test_ambiguous_match_llm_says_no(self) -> None:
        from ananta.explorers.arxiv.papers.verifiers import CascadingVerifier

        citation = ExtractedCitation(key="x", title="Chess Engine Analysis", authors=[], year=None)

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.UNRESOLVED,
            source="openalex",
            actual_title="Chess Board Manufacturing Analysis",
            message="Title match ambiguous (similarity=0.55)",
        )

        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "NO. Different papers."

        with patch(
            "ananta.explorers.arxiv.papers.verifiers.litellm.completion",
            return_value=mock_completion,
        ):
            verifier = CascadingVerifier(
                openalex_verifier=mock_openalex,
                semantic_scholar_verifier=mock_s2,
                model="test-model",
            )
            result = verifier.verify(citation)

        mock_s2.verify.assert_called_once()
        assert result.status == VerificationStatus.UNRESOLVED
