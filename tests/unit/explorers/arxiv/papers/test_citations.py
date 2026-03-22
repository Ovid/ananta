"""Tests for citation extraction and LLM-tell phrase detection."""

from __future__ import annotations

import pytest


class TestExtractFromBib:
    """Tests for .bib file citation extraction."""

    def test_extract_single_entry(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{smith2023quantum,
    author = {Smith, John and Doe, Alice},
    title = {Quantum Error Correction Survey},
    journal = {Physical Review Letters},
    year = {2023},
    eprint = {2301.04567},
}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 1
        assert cites[0].key == "smith2023quantum"
        assert cites[0].title == "Quantum Error Correction Survey"
        assert cites[0].year == "2023"
        assert cites[0].arxiv_id == "2301.04567"

    def test_extract_multiple_entries(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{a, author={A}, title={Paper A}, year={2023}}
@inproceedings{b, author={B}, title={Paper B}, year={2024}}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 2

    def test_extract_arxiv_id_from_eprint(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, eprint={2501.12345}, archivePrefix={arXiv}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].arxiv_id == "2501.12345"

    def test_extract_doi(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, doi={10.1234/example}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].doi == "10.1234/example"

    def test_empty_bib(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        assert extract_citations_from_bib("") == []

    def test_duplicate_keys_no_log_noise(self, caplog: pytest.LogCaptureFixture) -> None:
        """Duplicate bib keys must not emit warnings to the log."""
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{dup, author={A}, title={T1}, year={2020}}
@article{dup, author={B}, title={T2}, year={2021}}
"""
        with caplog.at_level("WARNING"):
            extract_citations_from_bib(bib)
        assert "Unknown block type" not in caplog.text

    def test_eprint_with_arxiv_prefix_normalized(self) -> None:
        """eprint = {arXiv:2301.04567} should store just '2301.04567'."""
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{prefixed,
    author = {X},
    title = {T},
    year = {2023},
    eprint = {arXiv:2301.04567},
}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 1
        assert cites[0].arxiv_id == "2301.04567"

    def test_eprint_url_not_treated_as_arxiv_id(self) -> None:
        """A URL in the eprint field must not be accepted as an arXiv ID."""
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        bib = """
@article{wiley2023,
    author = {Author},
    title = {Some Book Chapter},
    year = {2023},
    eprint = {https://onlinelibrary.wiley.com/doi/pdf/10.1002/9781119555568.ch16},
}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 1
        assert cites[0].arxiv_id is None

    def test_malformed_bib_does_not_crash(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bib

        # Malformed BibTeX should return empty, not crash
        result = extract_citations_from_bib("this is not valid bibtex {{{")
        assert isinstance(result, list)


class TestExtractFromBbl:
    """Tests for .bbl file citation extraction."""

    def test_extract_bibitem(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{10}

\bibitem{smith2023}
J.~Smith and A.~Doe.
\newblock Quantum error correction survey.
\newblock {\em Physical Review Letters}, 2023.

\bibitem{jones2024}
K.~Jones.
\newblock Surface codes revisited.
\newblock arXiv:2401.67890, 2024.

\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 2
        assert cites[0].key == "smith2023"
        assert cites[1].key == "jones2024"

    def test_extract_arxiv_id_from_bbl_text(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{1}
\bibitem{x}
Author. Title. arXiv:2301.04567, 2023.
\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 1
        assert cites[0].arxiv_id == "2301.04567"

    def test_empty_bbl(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_bbl

        assert extract_citations_from_bbl("") == []


class TestDetectLLMPhrases:
    """Tests for LLM-tell phrase detection."""

    def test_detect_knowledge_update_phrase(self) -> None:
        from ananta.explorers.arxiv.papers.citations import detect_llm_phrases

        text = "Line one.\nAs of my last knowledge update, this is true.\nLine three."
        results = detect_llm_phrases(text)
        assert len(results) == 1
        line_num, phrase = results[0]
        assert line_num == 2
        assert "knowledge update" in phrase.lower()

    def test_detect_important_to_note(self) -> None:
        from ananta.explorers.arxiv.papers.citations import detect_llm_phrases

        text = "It is important to note that the results suggest otherwise."
        results = detect_llm_phrases(text)
        assert len(results) == 1

    def test_no_false_positives_on_clean_text(self) -> None:
        from ananta.explorers.arxiv.papers.citations import detect_llm_phrases

        text = (
            "We present a novel method for quantum error correction.\nOur results show improvement."
        )
        results = detect_llm_phrases(text)
        assert results == []

    def test_detect_multiple_phrases(self) -> None:
        from ananta.explorers.arxiv.papers.citations import detect_llm_phrases

        text = (
            "As of my last knowledge update, X.\nNormal line.\nI cannot provide specific details.\n"
        )
        results = detect_llm_phrases(text)
        assert len(results) == 2

    def test_case_insensitive(self) -> None:
        from ananta.explorers.arxiv.papers.citations import detect_llm_phrases

        text = "AS OF MY LAST KNOWLEDGE UPDATE, things changed."
        results = detect_llm_phrases(text)
        assert len(results) == 1


class TestExtractFromText:
    """Tests for plain text (PDF-extracted) citation extraction."""

    def test_extract_arxiv_ids_from_text(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        text = (
            "We build on prior work [1] and extend the results of arXiv:2301.04567.\n"
            "See also arXiv:2502.67890v2 for related approaches.\n"
        )
        cites = extract_citations_from_text(text)
        assert len(cites) == 2
        ids = {c.arxiv_id for c in cites}
        assert "2301.04567" in ids
        assert "2502.67890v2" in ids

    def test_empty_text(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        assert extract_citations_from_text("") == []

    def test_no_arxiv_ids(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        text = "This paper has no arXiv references, only DOIs like 10.1234/example."
        assert extract_citations_from_text(text) == []

    def test_deduplicates_ids(self) -> None:
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        text = "We cite arXiv:2301.04567 here and again arXiv:2301.04567 there."
        cites = extract_citations_from_text(text)
        assert len(cites) == 1

    def test_requires_arxiv_context(self) -> None:
        """Bare IDs without arXiv context should not be extracted from text."""
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        text = "The parameter was 2301.04567 in our experiment."
        assert extract_citations_from_text(text) == []

    def test_extracts_with_arxiv_url(self) -> None:
        """IDs in arxiv.org URLs should be extracted."""
        from ananta.explorers.arxiv.papers.citations import extract_citations_from_text

        text = "Available at https://arxiv.org/abs/2301.04567v2."
        cites = extract_citations_from_text(text)
        assert len(cites) == 1
        assert cites[0].arxiv_id == "2301.04567v2"


class TestArxivIdPattern:
    """Tests for strict arXiv ID regex validation."""

    def test_valid_standard_id(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("2301.04567") is not None

    def test_valid_five_digit_id(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("2501.12345") is not None

    def test_valid_with_version(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("2301.04567v2") is not None

    def test_valid_with_arxiv_prefix(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        m = ARXIV_ID_PATTERN.fullmatch("arXiv:2301.04567")
        assert m is not None
        assert m.group(1) == "2301.04567"

    def test_valid_earliest_new_style(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # April 2007 was first new-style month
        assert ARXIV_ID_PATTERN.fullmatch("0704.0001") is not None

    def test_rejects_month_over_12(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # 2016.25840: month 16 > 12
        assert ARXIV_ID_PATTERN.fullmatch("2016.25840") is None

    def test_rejects_doi_fragment_9876(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # 9876.00159 from DOI 10.1111/1467-9876.00159
        assert ARXIV_ID_PATTERN.fullmatch("9876.00159") is None

    def test_rejects_doi_fragment_1149(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # 1149.11012 from DOI 10.1145/1101149.1101236
        assert ARXIV_ID_PATTERN.fullmatch("1149.11012") is None

    def test_rejects_year_before_07(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("0601.12345") is None

    def test_rejects_impossible_month_56(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("0156.13901") is None

    def test_rejects_impossible_month_65(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("5765.32358") is None

    def test_rejects_year_page_fragment(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # 8317.1983 from a year-based bib key
        assert ARXIV_ID_PATTERN.fullmatch("8317.1983") is None

    def test_rejects_month_00(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        assert ARXIV_ID_PATTERN.fullmatch("2300.12345") is None

    def test_search_does_not_match_doi_in_text(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ARXIV_ID_PATTERN

        # Should not extract arXiv IDs from DOI strings
        text = "doi:10.1111/1467-9876.00159"
        assert ARXIV_ID_PATTERN.search(text) is None


class TestVerificationStatusExtended:
    """Tests for new verification statuses."""

    def test_verified_external_status_exists(self) -> None:
        from ananta.explorers.arxiv.papers.models import VerificationStatus

        assert VerificationStatus.VERIFIED_EXTERNAL.value == "verified_external"

    def test_topically_unrelated_status_exists(self) -> None:
        from ananta.explorers.arxiv.papers.models import VerificationStatus

        assert VerificationStatus.TOPICALLY_UNRELATED.value == "topically_unrelated"


class TestVerificationResultSource:
    """Tests for source field on VerificationResult."""

    def test_source_defaults_to_none(self) -> None:
        from ananta.explorers.arxiv.papers.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED,
        )
        assert result.source is None

    def test_source_can_be_set(self) -> None:
        from ananta.explorers.arxiv.papers.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="crossref",
        )
        assert result.source == "crossref"


class TestCheckReportVerifiedExternal:
    """Tests that VERIFIED_EXTERNAL counts as verified."""

    def test_verified_external_counted_in_verified_count(self) -> None:
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        citations = [
            ExtractedCitation(key="a", title="T1", authors=[], year=None),
            ExtractedCitation(key="b", title="T2", authors=[], year=None),
        ]
        results = [
            VerificationResult(citation_key="a", status=VerificationStatus.VERIFIED),
            VerificationResult(
                citation_key="b", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
            ),
        ]
        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=citations,
            verification_results=results,
            llm_phrases=[],
        )
        assert report.verified_count == 2


class TestFuzzyTitleMatch:
    """Tests for Jaccard-based fuzzy title matching."""

    def test_exact_match_returns_high_score(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        assert title_similarity("Quantum Error Correction", "Quantum Error Correction") == 1.0

    def test_contained_title_returns_high_score(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        score = title_similarity("Chess Strategies", "Chess Strategies: A Survey")
        assert score >= 0.5

    def test_reordered_words_returns_high_score(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        score = title_similarity(
            "Learning to Play Chess from Textbooks",
            "From Textbooks Learning to Play Chess",
        )
        assert score >= 0.85

    def test_completely_different_returns_low_score(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        score = title_similarity(
            "Quantum Error Correction Survey",
            "Sentiment Analysis of Victorian Novels",
        )
        assert score < 0.5

    def test_acronym_expansion_moderate_score(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        score = title_similarity(
            "Learning Chess from Text",
            "LEAP: Learning to Play Chess from Textbooks",
        )
        # Should be in ambiguous range (0.5-0.85) — LLM would decide
        assert 0.3 < score < 1.0

    def test_empty_titles(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        assert title_similarity("", "") == 0.0

    def test_latex_commands_stripped(self) -> None:
        from ananta.explorers.arxiv.papers.citations import title_similarity

        score = title_similarity(
            r"\emph{Quantum} Error \textbf{Correction}",
            "Quantum Error Correction",
        )
        assert score == 1.0


class TestFormatCheckReportJsonExtended:
    """Tests for JSON report with new statuses."""

    def test_verified_external_grouped_as_verified(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="crossref",
                )
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "verified"

    def test_topically_unrelated_included_in_output(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[
                ExtractedCitation(key="a", title="Good", authors=[], year=None),
                ExtractedCitation(key="b", title="Bad", authors=[], year=None),
            ],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED,
                ),
                VerificationResult(
                    citation_key="b",
                    status=VerificationStatus.TOPICALLY_UNRELATED,
                    message="Literary analysis unrelated",
                    severity="warning",
                ),
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "issues"
        assert result["has_issues"] is True
        assert len(result["topical_issues"]) == 1
        assert result["topical_issues"][0]["key"] == "b"

    def test_source_badge_included_in_verified_entries(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="openalex",
                )
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert "sources" in result
        assert result["sources"]["a"] == "openalex"

    def test_unresolved_label_updated(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(citation_key="a", status=VerificationStatus.UNRESOLVED)
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "unverifiable"
