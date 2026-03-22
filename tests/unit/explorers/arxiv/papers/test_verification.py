"""Tests for citation verification and report formatting."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock


class TestArxivVerifier:
    """Tests for ArxivVerifier."""

    def test_verified_when_title_matches(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED

    def test_verified_when_title_has_bibtex_linebreaks(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="1811.06031",
            title="A Hierarchical Multi-task Approach for Learning Embeddings from Semantic Tasks",
            authors=["Sanh, V."],
            abstract="",
            published=datetime(2018, 11, 1, tzinfo=UTC),
            updated=datetime(2018, 11, 1, tzinfo=UTC),
            categories=["cs.CL"],
            primary_category="cs.CL",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/1811.06031v2",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="DBLP:journals/corr/abs-1811-06031",
            title=(
                "A Hierarchical Multi-task Approach for Learning Embeddings"
                " from Semantic\n               Tasks"
            ),
            authors=["Sanh, V."],
            year="2018",
            arxiv_id="1811.06031",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED

    def test_verified_when_title_has_latex_commands(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="1911.04090",
            title="A post hoc test on the Sharpe ratio",
            authors=["Pav, S."],
            abstract="",
            published=datetime(2019, 11, 1, tzinfo=UTC),
            updated=datetime(2019, 11, 1, tzinfo=UTC),
            categories=["stat.ME"],
            primary_category="stat.ME",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/1911.04090v1",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="pav2019posthoc",
            title=r"A \emph{post hoc} test on the {S}harpe ratio",
            authors=["Pav, S."],
            year="2019",
            arxiv_id="1911.04090",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED

    def test_mismatch_when_title_differs(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Fluid Dynamics of Turbulent Flow",
            authors=["Jones, K."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["physics.flu-dyn"],
            primary_category="physics.flu-dyn",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Memory Architectures",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.MISMATCH
        assert "Fluid Dynamics" in (result.actual_title or "")

    def test_not_found_when_id_missing(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import ExtractedCitation, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = None

        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="x",
            title="Nonexistent",
            authors=[],
            year="2023",
            arxiv_id="9999.99999",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.NOT_FOUND

    def test_unresolved_for_non_arxiv_citation(self) -> None:
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import ExtractedCitation, VerificationStatus

        verifier = ArxivVerifier(searcher=MagicMock())
        cite = ExtractedCitation(
            key="book2020",
            title="Some Book",
            authors=["Author"],
            year="2020",
            arxiv_id=None,
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_not_found_has_error_severity(self) -> None:
        """Non-existent arXiv IDs should have 'error' severity."""
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import ExtractedCitation, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = None

        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="x", title="Nonexistent", authors=[], year="2023", arxiv_id="2301.99999"
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.NOT_FOUND
        assert result.severity == "error"

    def test_mismatch_has_warning_severity(self) -> None:
        """Title mismatches should have 'warning' severity (could be version rename)."""
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Amortized Planning with Large-Scale Transformers",
            authors=["Author"],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="ruoss2024",
            title="Grandmaster-Level Chess Without Search",
            authors=["Author"],
            year="2024",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.MISMATCH
        assert result.severity == "warning"

    def test_verified_has_no_severity(self) -> None:
        """Verified citations should have None severity."""
        from ananta.explorers.arxiv.papers.citations import ArxivVerifier
        from ananta.explorers.arxiv.papers.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Quantum Error Correction Survey",
            authors=["Smith"],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction Survey",
            authors=["Smith"],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED
        assert result.severity is None


class TestFormatCheckReport:
    """Tests for report formatting."""

    def test_format_includes_disclaimer(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report
        from ananta.explorers.arxiv.papers.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "DISCLAIMER" in output
        assert "capable of making mistakes" in output

    def test_format_shows_mismatch_details(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="x",
            title="Quantum Memory",
            authors=[],
            year="2023",
            arxiv_id="2301.04567",
        )
        vr = VerificationResult(
            citation_key="x",
            status=VerificationStatus.MISMATCH,
            message='Cites "Quantum Memory" but actual paper is "Fluid Dynamics"',
            actual_title="Fluid Dynamics of Turbulent Flow",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "MISMATCH" in output or "X" in output
        assert "Fluid Dynamics" in output
        assert "2301.04567" in output

    def test_format_shows_llm_phrases_with_potential_label(self) -> None:
        from ananta.explorers.arxiv.papers.citations import format_check_report
        from ananta.explorers.arxiv.papers.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[(42, "As of my last knowledge update, X is true.")],
        )
        output = format_check_report(report)
        assert "42" in output
        assert "knowledge update" in output.lower()
        assert "Potential LLM-tell phrases found:" in output


class TestFormatCheckReportJson:
    """Tests for JSON report formatting."""

    def test_verified_paper_grouped_as_verified(self) -> None:
        """Paper with all citations verified → group 'verified'."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="a", title="Paper A", authors=[], year="2023", arxiv_id="2301.00001"
        )
        vr = VerificationResult(
            citation_key="a",
            status=VerificationStatus.VERIFIED,
            arxiv_url="https://arxiv.org/abs/2301.00001",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "verified"
        assert result["has_issues"] is False

    def test_unverifiable_paper_grouped_as_unverifiable(self) -> None:
        """Paper with unresolved citations but no mismatches → group 'unverifiable'."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="book", title="Some Book", authors=[], year="2020", arxiv_id=None
        )
        vr = VerificationResult(citation_key="book", status=VerificationStatus.UNRESOLVED)
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "unverifiable"
        assert result["has_issues"] is False

    def test_paper_with_mismatches_grouped_as_issues(self) -> None:
        """Paper with mismatches → group 'issues'."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="x", title="Wrong Title", authors=[], year="2023", arxiv_id="2301.00001"
        )
        vr = VerificationResult(
            citation_key="x",
            status=VerificationStatus.MISMATCH,
            message='Cites "Wrong" but actual is "Right"',
            actual_title="Right Title",
            arxiv_url="https://arxiv.org/abs/2301.00001",
            severity="warning",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "issues"
        assert result["has_issues"] is True
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["severity"] == "warning"

    def test_paper_with_llm_phrases_grouped_as_issues(self) -> None:
        """Paper with LLM-tell phrases → group 'issues'."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[(42, "As of my last knowledge update")],
        )
        result = format_check_report_json(report)
        assert result["group"] == "issues"
        assert result["has_issues"] is True
        assert len(result["llm_phrases"]) == 1

    def test_zero_citations_grouped_as_issues(self) -> None:
        """Paper with zero citations → group 'issues'."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "issues"
        assert result["total_citations"] == 0

    def test_json_structure_has_required_fields(self) -> None:
        """JSON output has all required fields."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        required = {
            "arxiv_id",
            "title",
            "arxiv_url",
            "total_citations",
            "verified_count",
            "unresolved_count",
            "mismatch_count",
            "has_issues",
            "group",
            "mismatches",
            "llm_phrases",
        }
        assert required.issubset(result.keys())

    def test_mismatch_entry_has_required_fields(self) -> None:
        """Each mismatch in JSON has key, message, severity, arxiv_url."""
        from ananta.explorers.arxiv.papers.citations import format_check_report_json
        from ananta.explorers.arxiv.papers.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(key="x", title="T", authors=[], year="2023", arxiv_id="2301.00001")
        vr = VerificationResult(
            citation_key="x",
            status=VerificationStatus.NOT_FOUND,
            message="arXiv ID 2301.00001 does not exist",
            severity="error",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        m = result["mismatches"][0]
        assert "key" in m
        assert "message" in m
        assert "severity" in m
        assert "arxiv_url" in m
