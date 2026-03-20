"""Tests for MultiRepoAnalyzer."""

import json
from unittest.mock import MagicMock

import pytest

from ananta.experimental.multi_repo import MultiRepoAnalyzer
from ananta.experimental.multi_repo.models import HLDDraft, ImpactReport, RepoSummary
from ananta.models import AnalysisComponent, RepoAnalysis


class TestMultiRepoAnalyzerInit:
    """Tests for analyzer initialization."""

    def test_init_with_ananta_instance(self):
        """Analyzer initializes with an Ananta instance."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)

        assert analyzer._ananta is mock_ananta
        assert analyzer._repos == []
        assert analyzer._summaries == {}
        assert analyzer._impacts == {}

    def test_init_with_custom_config(self):
        """Analyzer accepts custom configuration."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(
            mock_ananta,
            max_discovery_rounds=3,
            max_revision_rounds=4,
        )

        assert analyzer._max_discovery_rounds == 3
        assert analyzer._max_revision_rounds == 4

    def test_init_default_config(self):
        """Analyzer has sensible defaults."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)

        assert analyzer._max_discovery_rounds == 2
        assert analyzer._max_revision_rounds == 2


class TestMultiRepoAnalyzerProperties:
    """Tests for analyzer properties."""

    def test_repos_property(self):
        """repos property returns list of project_ids."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["repo-a", "repo-b"]

        assert analyzer.repos == ["repo-a", "repo-b"]

    def test_summaries_property(self):
        """summaries property returns dict of RepoSummary."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)

        summary = RepoSummary(project_id="test", raw_summary="text")
        analyzer._summaries = {"test": summary}

        assert analyzer.summaries == {"test": summary}

    def test_impacts_property(self):
        """impacts property returns dict of ImpactReport."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)

        report = ImpactReport(project_id="test", affected=True, raw_analysis="text")
        analyzer._impacts = {"test": report}

        assert analyzer.impacts == {"test": report}


class TestMultiRepoAnalyzerAddRepo:
    """Tests for add_repo method."""

    def test_add_repo_creates_project(self):
        """add_repo creates a project vian Ananta."""
        mock_ananta = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "created"
        mock_ananta.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_ananta)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        assert "org-repo" in analyzer.repos
        mock_ananta.create_project_from_repo.assert_called_once_with("https://github.com/org/repo")

    def test_add_repo_reuses_existing(self):
        """add_repo reuses existing project if unchanged."""
        mock_ananta = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "unchanged"
        mock_ananta.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_ananta)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        assert "org-repo" in analyzer.repos

    def test_add_repo_handles_updates(self):
        """add_repo applies updates if available."""
        mock_ananta = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "updates_available"
        mock_updated_result = MagicMock()
        mock_updated_result.project.project_id = "org-repo"
        mock_updated_result.status = "created"
        mock_result.apply_updates.return_value = mock_updated_result
        mock_ananta.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_ananta)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        mock_result.apply_updates.assert_called_once()

    def test_add_repo_avoids_duplicates(self):
        """add_repo doesn't add the same repo twice."""
        mock_ananta = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "unchanged"
        mock_ananta.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer.add_repo("https://github.com/org/repo")
        analyzer.add_repo("https://github.com/org/repo")

        assert analyzer.repos.count("org-repo") == 1


class TestMultiRepoAnalyzerRecon:
    """Tests for Phase 1 recon."""

    def test_run_recon_queries_project(self):
        """Recon phase queries the project with recon prompt."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "apis": ["GET /users"],
                    "models": ["User"],
                    "entry_points": ["main.py"],
                    "dependencies": ["postgres"],
                }
            )
            + "\n\nThis is a user service."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        summary = analyzer._run_recon("test-repo")

        assert summary.project_id == "test-repo"
        assert "GET /users" in summary.apis
        assert "User" in summary.models
        mock_project.query.assert_called_once()

    def test_run_recon_handles_malformed_json(self):
        """Recon gracefully handles non-JSON responses."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = "This repo contains user management code."
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        summary = analyzer._run_recon("test-repo")

        assert summary.project_id == "test-repo"
        assert summary.raw_summary == "This repo contains user management code."
        # Lists should be empty when JSON parsing fails
        assert summary.apis == []


class TestMultiRepoAnalyzerImpact:
    """Tests for Phase 2 impact analysis."""

    def test_run_impact_queries_with_prd_and_summary(self):
        """Impact phase queries with PRD and repo summary."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "affected": True,
                    "changes": ["Add new endpoint"],
                    "new_interfaces": ["GET /new"],
                    "modified_interfaces": ["POST /old"],
                    "discovered_dependencies": ["other-service"],
                }
            )
            + "\n\nNeeds changes for OAuth."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)

        summary = RepoSummary(
            project_id="test-repo",
            apis=["GET /users"],
            raw_summary="User service",
        )

        report = analyzer._run_impact("test-repo", "Add OAuth support", summary)

        assert report.project_id == "test-repo"
        assert report.affected is True
        assert "Add new endpoint" in report.changes
        assert "other-service" in report.discovered_dependencies

    def test_run_impact_not_affected(self):
        """Impact correctly identifies unaffected repos."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "affected": False,
                    "changes": [],
                    "new_interfaces": [],
                    "modified_interfaces": [],
                    "discovered_dependencies": [],
                }
            )
            + "\n\nNo changes needed."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)

        summary = RepoSummary(project_id="test-repo", raw_summary="Logging service")

        report = analyzer._run_impact("test-repo", "Add OAuth support", summary)

        assert report.affected is False
        assert report.changes == []


class TestMultiRepoAnalyzerSynthesize:
    """Tests for Phase 3 HLD synthesis."""

    def test_run_synthesize_creates_hld(self):
        """Synthesize phase creates HLD from impact reports."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "component_changes": {"auth": ["Add OAuth"]},
                    "data_flow": "User -> Auth -> API",
                    "interface_contracts": ["OAuth callback"],
                    "implementation_sequence": ["1. Auth", "2. API"],
                    "open_questions": ["Provider?"],
                }
            )
            + "\n\n# Full HLD\n\n## Changes\n..."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["auth"]

        impacts = {
            "auth": ImpactReport(
                project_id="auth",
                affected=True,
                changes=["Add OAuth"],
                raw_analysis="Needs OAuth",
            )
        }

        hld = analyzer._run_synthesize("Add OAuth support", impacts)

        assert hld.component_changes == {"auth": ["Add OAuth"]}
        assert hld.data_flow == "User -> Auth -> API"
        assert "Provider?" in hld.open_questions
        assert "# Full HLD" in hld.raw_hld


class TestMultiRepoAnalyzerAlign:
    """Tests for Phase 4 alignment verification."""

    def test_run_align_checks_coverage(self):
        """Align phase verifies HLD covers PRD."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "covered": [{"requirement": "R1", "hld_section": "S1"}],
                    "gaps": [],
                    "scope_creep": [],
                    "alignment_score": 1.0,
                    "recommendation": "approved",
                }
            )
            + "\n\nFully aligned."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test"]

        hld = HLDDraft(raw_hld="# HLD\n...")

        report = analyzer._run_align("PRD text", hld)

        assert report.alignment_score == 1.0
        assert report.recommendation == "approved"
        assert len(report.covered) == 1
        assert report.gaps == []

    def test_run_align_finds_gaps(self):
        """Align phase identifies missing requirements."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            json.dumps(
                {
                    "covered": [],
                    "gaps": [{"requirement": "R1", "reason": "Not addressed"}],
                    "scope_creep": [],
                    "alignment_score": 0.5,
                    "recommendation": "revise",
                }
            )
            + "\n\nNeeds revision."
        )
        mock_project.query.return_value = mock_query_result
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test"]

        hld = HLDDraft(raw_hld="# HLD\n...")

        report = analyzer._run_align("PRD text", hld)

        assert report.alignment_score == 0.5
        assert report.recommendation == "revise"
        assert len(report.gaps) == 1


class TestMultiRepoAnalyzerAnalyze:
    """Tests for main analyze method."""

    def test_analyze_without_repos_raises_valueerror(self):
        """analyze() raises ValueError when no repos added."""
        mock_ananta = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_ananta)

        with pytest.raises(ValueError, match="No repos added"):
            analyzer.analyze("Some PRD")

    def test_analyze_runs_all_phases(self):
        """analyze() runs all four phases."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {
                "apis": ["GET /users"],
                "models": ["User"],
                "entry_points": ["main.py"],
                "dependencies": [],
            }
        )

        # Impact response
        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": ["Add feature"],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        # Synthesize response
        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {"test-repo": ["Add feature"]},
                    "data_flow": "A -> B",
                    "interface_contracts": [],
                    "implementation_sequence": ["1. Do thing"],
                    "open_questions": [],
                }
            )
            + "\n\n# HLD"
        )

        # Align response
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [{"requirement": "R1", "hld_section": "S1"}],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_ananta.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        hld, alignment = analyzer.analyze("Add a feature")

        assert mock_project.query.call_count == 4
        assert alignment.recommendation == "approved"
        assert "test-repo" in hld.component_changes

    def test_analyze_calls_discovery_callback(self):
        """analyze() invokes on_discovery when deps found."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {
                "apis": [],
                "models": [],
                "entry_points": [],
                "dependencies": [],
            }
        )

        # Impact response with discovery
        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": ["other-service"],
            }
        )

        # Synthesize response
        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n\n# HLD"
        )

        # Align response
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_ananta.get_project.return_value = mock_project

        discovery_callback = MagicMock(return_value=None)  # None = skip adding

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_discovery=discovery_callback)

        discovery_callback.assert_called_once_with("other-service")

    def test_analyze_adds_discovered_repo_when_url_returned(self):
        """analyze() adds discovered repo when callback returns URL."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Setup for discovered repo
        mock_discovered_project = MagicMock()
        mock_discovered_project.project_id = "other-service"

        mock_discovered_result = MagicMock()
        mock_discovered_result.project.project_id = "other-service"
        mock_discovered_result.status = "created"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {"apis": [], "models": [], "entry_points": [], "dependencies": []}
        )

        # Impact response with discovery
        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": ["other-service"],
            }
        )

        # Synthesize response
        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n\n# HLD"
        )

        # Align response
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        # Query calls: recon(test-repo), impact(test-repo), recon(other-service),
        # impact(other-service), synthesize, align
        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            recon_result,  # recon for discovered repo
            impact_result,  # impact for discovered repo (no new discoveries)
            synth_result,
            align_result,
        ]

        def get_project(project_id: str) -> MagicMock:
            if project_id == "other-service":
                return mock_discovered_project
            return mock_project

        mock_ananta.get_project.side_effect = get_project
        mock_ananta.create_project_from_repo.return_value = mock_discovered_result
        mock_discovered_project.query.side_effect = [recon_result, impact_result]

        # Discovery callback returns URL for the discovered service
        discovery_callback = MagicMock(return_value="https://github.com/org/other-service")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_discovery=discovery_callback)

        # Should have called add_repo with the URL
        mock_ananta.create_project_from_repo.assert_called_once_with(
            "https://github.com/org/other-service"
        )
        # Discovered repo should be in the repos list
        assert "other-service" in analyzer.repos

    def test_analyze_calls_progress_callback(self):
        """analyze() invokes on_progress during phases."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Simple responses for all phases
        simple_result = MagicMock()
        simple_result.answer = json.dumps(
            {
                "apis": [],
                "models": [],
                "entry_points": [],
                "dependencies": [],
                "affected": False,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
                "component_changes": {},
                "data_flow": "",
                "interface_contracts": [],
                "implementation_sequence": [],
                "open_questions": [],
                "covered": [],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )
        mock_project.query.return_value = simple_result
        mock_ananta.get_project.return_value = mock_project

        progress_callback = MagicMock()

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_progress=progress_callback)

        # Should have progress calls for each phase
        phases_reported = [call[0][0] for call in progress_callback.call_args_list]
        assert "recon" in phases_reported
        assert "impact" in phases_reported
        assert "synthesize" in phases_reported
        assert "align" in phases_reported


class TestMultiRepoAnalyzerRevisionLoop:
    """Tests for alignment revision loop."""

    def test_revision_loop_runs_when_callback_returns_revise(self):
        """Revision loop re-synthesizes when on_alignment_issue returns 'revise'."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {
                "apis": [],
                "models": [],
                "entry_points": [],
                "dependencies": [],
            }
        )

        # Impact response
        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        # First synthesize - has gaps
        synth_result_1 = MagicMock()
        synth_result_1.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD v1"
        )

        # First align - recommends revise
        align_result_1 = MagicMock()
        align_result_1.answer = json.dumps(
            {
                "covered": [],
                "gaps": [{"requirement": "R1", "reason": "Missing"}],
                "scope_creep": [],
                "alignment_score": 0.5,
                "recommendation": "revise",
            }
        )

        # Second synthesize - fixed
        synth_result_2 = MagicMock()
        synth_result_2.answer = (
            json.dumps(
                {
                    "component_changes": {"test": ["Fixed"]},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD v2"
        )

        # Second align - approved
        align_result_2 = MagicMock()
        align_result_2.answer = json.dumps(
            {
                "covered": [{"requirement": "R1", "hld_section": "S1"}],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result_1,
            align_result_1,
            synth_result_2,
            align_result_2,
        ]
        mock_ananta.get_project.return_value = mock_project

        # Callback returns "revise" once
        alignment_callback = MagicMock(return_value="revise")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        hld, alignment = analyzer.analyze("PRD", on_alignment_issue=alignment_callback)

        # Should have called query 6 times (recon + impact + synth + align + synth + align)
        assert mock_project.query.call_count == 6
        assert alignment.recommendation == "approved"
        assert "HLD v2" in hld.raw_hld
        alignment_callback.assert_called_once()

    def test_revision_loop_passes_alignment_feedback(self):
        """Revision loop passes alignment gaps to synthesis prompt."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {"apis": [], "models": [], "entry_points": [], "dependencies": []}
        )

        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        synth_result_1 = MagicMock()
        synth_result_1.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD v1"
        )

        # Align finds gaps
        align_result_1 = MagicMock()
        align_result_1.answer = json.dumps(
            {
                "covered": [],
                "gaps": [{"requirement": "Auth flow", "reason": "Not addressed"}],
                "scope_creep": [{"hld_item": "Caching", "reason": "Not in PRD"}],
                "alignment_score": 0.5,
                "recommendation": "revise",
            }
        )

        synth_result_2 = MagicMock()
        synth_result_2.answer = (
            json.dumps(
                {
                    "component_changes": {"auth": ["Added"]},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD v2"
        )

        align_result_2 = MagicMock()
        align_result_2.answer = json.dumps(
            {
                "covered": [{"requirement": "Auth flow", "hld_section": "auth"}],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result_1,
            align_result_1,
            synth_result_2,
            align_result_2,
        ]
        mock_ananta.get_project.return_value = mock_project

        alignment_callback = MagicMock(return_value="revise")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_alignment_issue=alignment_callback)

        # Check that the second synthesize call included alignment feedback
        calls = mock_project.query.call_args_list
        # Call 4 (index 4) is the second synthesize call
        second_synth_prompt = calls[4][0][0]
        assert "Auth flow" in second_synth_prompt, "Gaps should be in revision prompt"
        assert "Caching: Not in PRD" in second_synth_prompt, (
            "Scope creep hld_item should appear as label, not 'Unknown'"
        )

    def test_revision_loop_stops_on_accept(self):
        """Revision loop stops immediately when callback returns 'accept'."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {"apis": [], "models": [], "entry_points": [], "dependencies": []}
        )

        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD"
        )

        # Align recommends revise but we'll accept
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [{"requirement": "R1", "reason": "Missing"}],
                "scope_creep": [],
                "alignment_score": 0.5,
                "recommendation": "revise",
            }
        )

        mock_project.query.side_effect = [recon_result, impact_result, synth_result, align_result]
        mock_ananta.get_project.return_value = mock_project

        # Callback returns "accept" - stop loop
        alignment_callback = MagicMock(return_value="accept")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        _, alignment = analyzer.analyze("PRD", on_alignment_issue=alignment_callback)

        # Only 4 queries - no revision loop
        assert mock_project.query.call_count == 4
        assert alignment.recommendation == "revise"  # Still revise, but we accepted
        alignment_callback.assert_called_once()

    def test_revision_loop_respects_max_rounds(self):
        """Revision loop stops after max_revision_rounds even if issues remain."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {"apis": [], "models": [], "entry_points": [], "dependencies": []}
        )

        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD"
        )

        # Align always recommends revise
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [{"requirement": "R1", "reason": "Still missing"}],
                "scope_creep": [],
                "alignment_score": 0.5,
                "recommendation": "revise",
            }
        )

        # Will be called: recon, impact, synth, align, synth, align, synth, align (max 2 rounds)
        # Initial: recon + impact + synth + align
        # Round 1: synth + align (callback returns "revise")
        # Round 2: synth + align (callback returns "revise", but max rounds hit)
        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
            synth_result,
            align_result,
            synth_result,
            align_result,
        ]
        mock_ananta.get_project.return_value = mock_project

        # Always returns "revise"
        alignment_callback = MagicMock(return_value="revise")

        analyzer = MultiRepoAnalyzer(mock_ananta, max_revision_rounds=2)
        analyzer._repos = ["test-repo"]

        _, alignment = analyzer.analyze("PRD", on_alignment_issue=alignment_callback)

        # 8 queries: recon + impact + synth + align + synth + align + synth + align
        assert mock_project.query.call_count == 8
        # Callback called twice (once per revision round)
        assert alignment_callback.call_count == 2
        # Final alignment still recommends revise (max rounds hit)
        assert alignment.recommendation == "revise"

    def test_major_gaps_triggers_alignment_callback(self):
        """Alignment callback fires for 'major_gaps', not just 'revise'."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {"apis": [], "models": [], "entry_points": [], "dependencies": []}
        )

        impact_result = MagicMock()
        impact_result.answer = json.dumps(
            {
                "affected": True,
                "changes": [],
                "new_interfaces": [],
                "modified_interfaces": [],
                "discovered_dependencies": [],
            }
        )

        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD"
        )

        # Align returns major_gaps (not just "revise")
        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [{"requirement": "R1", "reason": "Not addressed"}],
                "scope_creep": [],
                "alignment_score": 0.0,
                "recommendation": "major_gaps",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_ananta.get_project.return_value = mock_project

        # Callback returns "accept" — user sees the issue, accepts as-is
        alignment_callback = MagicMock(return_value="accept")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        _, alignment = analyzer.analyze("PRD", on_alignment_issue=alignment_callback)

        # Callback MUST be called for major_gaps
        alignment_callback.assert_called_once()
        assert alignment.recommendation == "major_gaps"


class TestMultiRepoAnalyzerErrorHandling:
    """Tests for error handling."""

    def test_add_repo_failure_is_tracked(self):
        """add_repo tracks failures without raising."""
        mock_ananta = MagicMock()
        mock_ananta.create_project_from_repo.side_effect = Exception("Clone failed")

        analyzer = MultiRepoAnalyzer(mock_ananta)
        project_id = analyzer.add_repo("https://github.com/org/bad-repo")

        assert project_id is None
        assert "https://github.com/org/bad-repo" in analyzer.failed_repos
        assert len(analyzer.repos) == 0

    def test_analyze_warns_on_large_context(self):
        """analyze warns when context approaches limits."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Create a very large impact analysis
        large_analysis = "x" * 600_000  # > 500KB

        recon_result = MagicMock()
        recon_result.answer = json.dumps(
            {
                "apis": [],
                "models": [],
                "entry_points": [],
                "dependencies": [],
            }
        )

        impact_result = MagicMock()
        impact_result.answer = (
            json.dumps(
                {
                    "affected": True,
                    "changes": [],
                    "new_interfaces": [],
                    "modified_interfaces": [],
                    "discovered_dependencies": [],
                }
            )
            + large_analysis
        )

        synth_result = MagicMock()
        synth_result.answer = (
            json.dumps(
                {
                    "component_changes": {},
                    "data_flow": "",
                    "interface_contracts": [],
                    "implementation_sequence": [],
                    "open_questions": [],
                }
            )
            + "\n# HLD"
        )

        align_result = MagicMock()
        align_result.answer = json.dumps(
            {
                "covered": [],
                "gaps": [],
                "scope_creep": [],
                "alignment_score": 1.0,
                "recommendation": "approved",
            }
        )

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_ananta.get_project.return_value = mock_project

        progress_messages = []

        def on_progress(phase: str, message: str) -> None:
            progress_messages.append((phase, message))

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_progress=on_progress)

        # Should have a warning about context size
        warning_found = any(
            "large" in msg.lower() or "context" in msg.lower()
            for phase, msg in progress_messages
            if phase == "synthesize"
        )
        assert warning_found, f"Expected context warning, got: {progress_messages}"


class TestAnalyzerWithAnalysis:
    """Tests for analyzer using existing analysis."""

    def test_run_recon_uses_analysis_when_available(self):
        """_run_recon injects analysis context when available."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_ananta.get_project.return_value = mock_project

        # Mock query result
        mock_query_result = MagicMock()
        mock_query_result.answer = (
            '{"apis": [], "models": [], "entry_points": [], "dependencies": []}'
        )
        mock_project.query.return_value = mock_query_result

        # Create analysis
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="A test service.",
            components=[
                AnalysisComponent(
                    name="API",
                    path="api/",
                    description="REST API",
                    apis=[{"type": "rest", "endpoints": ["/users"]}],
                    models=["User"],
                    entry_points=["main.py"],
                    internal_dependencies=[],
                )
            ],
            external_dependencies=[],
        )
        mock_ananta.get_analysis.return_value = analysis

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        # Run recon
        analyzer._run_recon("test-repo")

        # Verify query was called with analysis context
        call_args = mock_project.query.call_args
        prompt = call_args[0][0]
        assert "A test service." in prompt or "existing analysis" in prompt.lower()

    def test_run_recon_without_analysis_uses_standard_prompt(self):
        """_run_recon uses standard prompt when no analysis exists."""
        mock_ananta = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_ananta.get_project.return_value = mock_project

        mock_query_result = MagicMock()
        mock_query_result.answer = (
            '{"apis": [], "models": [], "entry_points": [], "dependencies": []}'
        )
        mock_project.query.return_value = mock_query_result

        # No analysis available
        mock_ananta.get_analysis.return_value = None

        analyzer = MultiRepoAnalyzer(mock_ananta)
        analyzer._repos = ["test-repo"]

        analyzer._run_recon("test-repo")

        # Verify standard prompt was used (no analysis context)
        call_args = mock_project.query.call_args
        prompt = call_args[0][0]
        assert "existing analysis" not in prompt.lower()
