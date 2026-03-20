"""Tests for arXiv explorer data models."""

from __future__ import annotations

from datetime import UTC, datetime


class TestPaperMeta:
    """Tests for PaperMeta dataclass."""

    def test_create_paper_meta(self) -> None:
        from ananta.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
            authors=["Smith, J.", "Doe, A."],
            abstract="A test abstract.",
            published=datetime(2025, 1, 15, tzinfo=UTC),
            updated=datetime(2025, 1, 15, tzinfo=UTC),
            categories=["cs.AI", "cs.CL"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        assert meta.arxiv_id == "2501.12345"
        assert meta.title == "Test Paper"
        assert len(meta.authors) == 2
        assert meta.primary_category == "cs.AI"

    def test_paper_meta_optional_fields(self) -> None:
        from ananta.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        assert meta.comment is None
        assert meta.journal_ref is None
        assert meta.doi is None
        assert meta.source_type is None

    def test_paper_meta_to_dict_roundtrip(self) -> None:
        """PaperMeta can serialize to dict and back for JSON storage."""
        from ananta.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        d = meta.to_dict()
        restored = PaperMeta.from_dict(d)
        assert restored.arxiv_id == meta.arxiv_id
        assert restored.title == meta.title
        assert restored.source_type == "latex"
        assert restored.published == meta.published


class TestExtractedCitation:
    """Tests for ExtractedCitation dataclass."""

    def test_create_citation(self) -> None:
        from ananta.experimental.arxiv.models import ExtractedCitation

        cite = ExtractedCitation(
            key="smith2023",
            title="Some Paper Title",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        assert cite.key == "smith2023"
        assert cite.arxiv_id == "2301.04567"

    def test_citation_without_arxiv_id(self) -> None:
        from ananta.experimental.arxiv.models import ExtractedCitation

        cite = ExtractedCitation(
            key="doe2022",
            title="Journal Paper",
            authors=["Doe, A."],
            year="2022",
        )
        assert cite.arxiv_id is None
        assert cite.doi is None


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verified_citation(self) -> None:
        from ananta.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="smith2023",
            status=VerificationStatus.VERIFIED,
        )
        assert result.status == VerificationStatus.VERIFIED
        assert result.message is None

    def test_mismatched_citation(self) -> None:
        from ananta.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="smith2023",
            status=VerificationStatus.MISMATCH,
            message='Cites "Quantum Memory" but actual paper is "Fluid Dynamics"',
            actual_title="Fluid Dynamics of Turbulent Flow",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        assert result.status == VerificationStatus.MISMATCH
        assert "Fluid Dynamics" in result.message


class TestTopicInfo:
    """Tests for TopicInfo dataclass."""

    def test_create_topic_info(self) -> None:
        from ananta.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="quantum-error-correction",
            created=datetime(2025, 1, 15, tzinfo=UTC),
            paper_count=3,
            size_bytes=12_400_000,
            project_id="2025-01-15-quantum-error-correction",
        )
        assert info.name == "quantum-error-correction"
        assert info.paper_count == 3

    def test_topic_info_formatted_size(self) -> None:
        from ananta.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="test",
            created=datetime(2025, 1, 1, tzinfo=UTC),
            paper_count=1,
            size_bytes=12_400_000,
            project_id="2025-01-01-test",
        )
        assert info.formatted_size == "12.4 MB"

    def test_topic_info_formatted_size_kb(self) -> None:
        from ananta.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="test",
            created=datetime(2025, 1, 1, tzinfo=UTC),
            paper_count=0,
            size_bytes=500,
            project_id="2025-01-01-test",
        )
        assert info.formatted_size == "0.5 KB"


class TestCheckReport:
    """Tests for CheckReport dataclass."""

    def test_create_check_report(self) -> None:
        from ananta.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(key="a", title="T", authors=["A"], year="2023")
        vr = VerificationResult(citation_key="a", status=VerificationStatus.VERIFIED)
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        assert report.verified_count == 1
        assert report.mismatch_count == 0
        assert report.unresolved_count == 0


class TestCitationVerifierProtocol:
    """Tests for the CitationVerifier Protocol."""

    def test_arxiv_verifier_satisfies_protocol(self) -> None:
        """ArxivVerifier should satisfy the CitationVerifier Protocol."""
        from ananta.experimental.arxiv.models import CitationVerifier

        # Verify the protocol has the expected method signature
        assert hasattr(CitationVerifier, "verify")
