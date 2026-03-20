"""Tests for multi-repo data models."""

from ananta.experimental.multi_repo.models import (
    AlignmentReport,
    HLDDraft,
    ImpactReport,
    RepoSummary,
)


class TestRepoSummary:
    """Tests for RepoSummary dataclass."""

    def test_create_repo_summary(self):
        """RepoSummary can be created with all fields."""
        summary = RepoSummary(
            project_id="auth-service",
            apis=["POST /login", "GET /user"],
            models=["User", "Session"],
            entry_points=["main.py"],
            dependencies=["postgres", "redis"],
            raw_summary="Full summary text",
        )

        assert summary.project_id == "auth-service"
        assert summary.apis == ["POST /login", "GET /user"]
        assert summary.models == ["User", "Session"]
        assert summary.entry_points == ["main.py"]
        assert summary.dependencies == ["postgres", "redis"]
        assert summary.raw_summary == "Full summary text"

    def test_repo_summary_defaults_to_empty_lists(self):
        """RepoSummary fields default to empty lists."""
        summary = RepoSummary(
            project_id="test",
            raw_summary="text",
        )

        assert summary.apis == []
        assert summary.models == []
        assert summary.entry_points == []
        assert summary.dependencies == []


class TestImpactReport:
    """Tests for ImpactReport dataclass."""

    def test_create_impact_report(self):
        """ImpactReport can be created with all fields."""
        report = ImpactReport(
            project_id="auth-service",
            affected=True,
            changes=["Add OAuth endpoint"],
            new_interfaces=["GET /oauth/callback"],
            modified_interfaces=["POST /login"],
            discovered_dependencies=["oauth-provider"],
            raw_analysis="Full analysis",
        )

        assert report.project_id == "auth-service"
        assert report.affected is True
        assert report.changes == ["Add OAuth endpoint"]
        assert report.new_interfaces == ["GET /oauth/callback"]
        assert report.modified_interfaces == ["POST /login"]
        assert report.discovered_dependencies == ["oauth-provider"]
        assert report.raw_analysis == "Full analysis"

    def test_impact_report_defaults(self):
        """ImpactReport fields have sensible defaults."""
        report = ImpactReport(
            project_id="test",
            affected=False,
            raw_analysis="text",
        )

        assert report.changes == []
        assert report.new_interfaces == []
        assert report.modified_interfaces == []
        assert report.discovered_dependencies == []


class TestHLDDraft:
    """Tests for HLDDraft dataclass."""

    def test_create_hld_draft(self):
        """HLDDraft can be created with all fields."""
        hld = HLDDraft(
            component_changes={"auth": ["Add OAuth"], "api": ["New endpoint"]},
            data_flow="User -> Auth -> API",
            interface_contracts=["OAuth callback spec"],
            implementation_sequence=["1. Auth changes", "2. API changes"],
            open_questions=["Which OAuth provider?"],
            raw_hld="# Full HLD\n...",
        )

        assert hld.component_changes == {"auth": ["Add OAuth"], "api": ["New endpoint"]}
        assert hld.data_flow == "User -> Auth -> API"
        assert hld.interface_contracts == ["OAuth callback spec"]
        assert hld.implementation_sequence == ["1. Auth changes", "2. API changes"]
        assert hld.open_questions == ["Which OAuth provider?"]
        assert hld.raw_hld == "# Full HLD\n..."

    def test_hld_draft_defaults(self):
        """HLDDraft fields have sensible defaults."""
        hld = HLDDraft(raw_hld="# HLD")

        assert hld.component_changes == {}
        assert hld.data_flow == ""
        assert hld.interface_contracts == []
        assert hld.implementation_sequence == []
        assert hld.open_questions == []


class TestAlignmentReport:
    """Tests for AlignmentReport dataclass."""

    def test_create_alignment_report(self):
        """AlignmentReport can be created with all fields."""
        report = AlignmentReport(
            covered=[{"requirement": "R1", "hld_section": "S1"}],
            gaps=[{"requirement": "R2", "reason": "Not addressed"}],
            scope_creep=[{"hld_item": "Extra feature", "reason": "Not in PRD"}],
            alignment_score=0.85,
            recommendation="revise",
            raw_analysis="Full alignment analysis",
        )

        assert report.covered == [{"requirement": "R1", "hld_section": "S1"}]
        assert report.gaps == [{"requirement": "R2", "reason": "Not addressed"}]
        assert report.scope_creep == [{"hld_item": "Extra feature", "reason": "Not in PRD"}]
        assert report.alignment_score == 0.85
        assert report.recommendation == "revise"
        assert report.raw_analysis == "Full alignment analysis"

    def test_alignment_report_defaults(self):
        """AlignmentReport fields have sensible defaults."""
        report = AlignmentReport(
            alignment_score=1.0,
            recommendation="approved",
            raw_analysis="text",
        )

        assert report.covered == []
        assert report.gaps == []
        assert report.scope_creep == []
