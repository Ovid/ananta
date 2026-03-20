"""Multi-repo PRD analyzer using federated queries."""

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from shesha.experimental.multi_repo.models import (
    AlignmentReport,
    HLDDraft,
    ImpactReport,
    RepoSummary,
)

if TYPE_CHECKING:
    from shesha import Shesha
    from shesha.models import RepoAnalysis

logger = logging.getLogger(__name__)


class MultiRepoAnalyzer:
    """Federated PRD analysis across multiple repositories.

    Coordinates analysis of how a PRD impacts multiple codebases,
    running queries against individual projects and synthesizing
    results into a draft HLD.

    Note:
        Timeout enforcement is not yet implemented. Queries use the
        default timeouts from the underlying RLM engine. This is a
        known limitation that requires architectural changes to address.
    """

    def __init__(
        self,
        shesha: "Shesha",
        max_discovery_rounds: int = 2,
        max_revision_rounds: int = 2,
    ) -> None:
        """Initialize the analyzer.

        Args:
            shesha: Shesha instance for project management.
            max_discovery_rounds: Max rounds of discovering new repos (default 2).
            max_revision_rounds: Max rounds of HLD revision (default 2).
        """
        self._shesha = shesha
        self._max_discovery_rounds = max_discovery_rounds
        self._max_revision_rounds = max_revision_rounds

        self._repos: list[str] = []
        self._summaries: dict[str, RepoSummary] = {}
        self._impacts: dict[str, ImpactReport] = {}
        self._failed_repos: dict[str, str] = {}

    @property
    def repos(self) -> list[str]:
        """List of project_ids currently in the analysis."""
        return self._repos

    @property
    def summaries(self) -> dict[str, RepoSummary]:
        """Recon summaries by project_id (populated after Phase 1)."""
        return self._summaries

    @property
    def impacts(self) -> dict[str, ImpactReport]:
        """Impact reports by project_id (populated after Phase 2)."""
        return self._impacts

    @property
    def failed_repos(self) -> dict[str, str]:
        """Repos that failed to add, with error messages."""
        return self._failed_repos

    def add_repo(self, url_or_path: str) -> str | None:
        """Add a repo to the analysis.

        If the repo was previously indexed, reuses it (with update check).
        If updates are available, they are automatically applied.

        Args:
            url_or_path: Git repository URL or local filesystem path.

        Returns:
            The project_id for the added repository, or None if failed.
        """
        try:
            result = self._shesha.create_project_from_repo(url_or_path)

            # Apply updates if available
            if result.status == "updates_available":
                result = result.apply_updates()

            project_id = result.project.project_id

            # Avoid duplicates
            if project_id not in self._repos:
                self._repos.append(project_id)

            return project_id
        except Exception as e:
            logger.warning("Failed to add repo %s: %s", url_or_path, e, exc_info=True)
            self._failed_repos[url_or_path] = str(e)
            return None

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from the prompts directory."""
        prompts_dir = Path(__file__).parent / "prompts"
        return (prompts_dir / f"{name}.md").read_text()

    def _format_analysis_context(self, analysis: "RepoAnalysis") -> str:
        """Format analysis for injection into recon prompt.

        Args:
            analysis: The analysis to format.

        Returns:
            Formatted string for prompt injection.
        """
        lines = [f"Overview: {analysis.overview}", "", "Components:"]

        for comp in analysis.components:
            lines.append(f"- {comp.name} ({comp.path}): {comp.description}")
            if comp.apis:
                for api in comp.apis:
                    api_type = api.get("type", "unknown")
                    endpoints = api.get("endpoints", [])
                    if endpoints:
                        lines.append(f"  APIs ({api_type}): {', '.join(endpoints[:5])}")
            if comp.models:
                lines.append(f"  Models: {', '.join(comp.models)}")

        if analysis.external_dependencies:
            lines.append("")
            lines.append("External Dependencies:")
            for dep in analysis.external_dependencies:
                lines.append(f"- {dep.name} ({dep.type}): {dep.description}")

        return "\n".join(lines)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON object from text that may contain markdown.

        Note: Similar to AnalysisGenerator._extract_json, but with a
        fast-path optimization for large multi-repo responses. Keep both
        until a third call site justifies a shared utility.
        """
        # Try to find JSON in code blocks first (greedy match for nested braces)
        json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                result: dict[str, Any] = json.loads(json_match.group(1))
                return result
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON by looking for balanced braces
        start_idx = text.find("{")
        if start_idx == -1:
            return None

        # Fast path: try first { to last } (covers most valid JSON responses)
        end_idx = text.rfind("}")
        if end_idx > start_idx:
            try:
                return cast(dict[str, Any], json.loads(text[start_idx : end_idx + 1]))
            except json.JSONDecodeError:
                pass  # Fall through to slower search

        # Slow path: try progressively shorter substrings
        for end_idx in range(len(text) - 1, start_idx, -1):
            if text[end_idx] == "}":
                try:
                    return cast(dict[str, Any], json.loads(text[start_idx : end_idx + 1]))
                except json.JSONDecodeError:
                    continue

        return None

    def _run_recon(self, project_id: str) -> RepoSummary:
        """Run Phase 1 recon on a single project.

        Args:
            project_id: The project to analyze.

        Returns:
            RepoSummary with extracted structure.
        """
        project = self._shesha.get_project(project_id)

        # Check for existing analysis
        analysis = self._shesha.get_analysis(project_id)

        if analysis:
            # Use analysis-enhanced prompt
            context = self._format_analysis_context(analysis)
            prompt_template = self._load_prompt("recon_with_analysis")
            prompt = prompt_template.replace("{existing_analysis}", context)
        else:
            # Use standard recon prompt
            prompt = self._load_prompt("recon")

        result = project.query(prompt)
        answer = result.answer

        # Try to extract structured data
        data = self._extract_json(answer)

        if data:
            return RepoSummary(
                project_id=project_id,
                apis=data.get("apis", []),
                models=data.get("models", []),
                entry_points=data.get("entry_points", []),
                dependencies=data.get("dependencies", []),
                raw_summary=answer,
            )

        # Fallback: return raw answer with empty lists
        return RepoSummary(
            project_id=project_id,
            raw_summary=answer,
        )

    def _run_impact(
        self,
        project_id: str,
        prd: str,
        summary: RepoSummary,
    ) -> ImpactReport:
        """Run Phase 2 impact analysis on a single project."""
        project = self._shesha.get_project(project_id)
        prompt_template = self._load_prompt("impact")

        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{repo_summary}", summary.raw_summary)

        result = project.query(prompt)
        answer = result.answer

        data = self._extract_json(answer)

        if data:
            return ImpactReport(
                project_id=project_id,
                affected=data.get("affected", False),
                changes=data.get("changes", []),
                new_interfaces=data.get("new_interfaces", []),
                modified_interfaces=data.get("modified_interfaces", []),
                discovered_dependencies=data.get("discovered_dependencies", []),
                raw_analysis=answer,
            )

        return ImpactReport(
            project_id=project_id,
            affected=True,
            raw_analysis=answer,
        )

    def _run_synthesize(
        self,
        prd: str,
        impacts: dict[str, ImpactReport],
        alignment_feedback: AlignmentReport | None = None,
    ) -> HLDDraft:
        """Run Phase 3 HLD synthesis.

        Args:
            prd: The PRD text.
            impacts: Impact reports from Phase 2.
            alignment_feedback: Optional alignment report from previous iteration.
                If provided, the synthesis will be guided to address gaps and
                remove scope creep identified in the alignment.
        """
        project = self._shesha.get_project(self._repos[0])
        prompt_template = self._load_prompt("synthesize")

        impact_text = "\n\n".join(
            f"### {pid}\n{report.raw_analysis}" for pid, report in impacts.items()
        )

        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{impact_reports}", impact_text)

        # Add alignment feedback for revision iterations
        if alignment_feedback is not None:
            feedback_sections = []

            if alignment_feedback.gaps:
                gaps_text = "\n".join(
                    f"- {g.get('requirement', 'Unknown')}: {g.get('reason', 'No reason')}"
                    for g in alignment_feedback.gaps
                )
                feedback_sections.append(f"**Gaps to address:**\n{gaps_text}")

            if alignment_feedback.scope_creep:
                creep_text = "\n".join(
                    f"- {s.get('hld_item', 'Unknown')}: {s.get('reason', 'No reason')}"
                    for s in alignment_feedback.scope_creep
                )
                feedback_sections.append(f"**Scope creep to remove:**\n{creep_text}")

            if feedback_sections:
                prompt += "\n\n## Alignment Feedback (from previous review)\n\n"
                prompt += "\n\n".join(feedback_sections)
                prompt += "\n\nPlease revise the HLD to address these issues."

        result = project.query(prompt)
        answer = result.answer

        data = self._extract_json(answer)

        if data:
            return HLDDraft(
                component_changes=data.get("component_changes", {}),
                data_flow=data.get("data_flow", ""),
                interface_contracts=data.get("interface_contracts", []),
                implementation_sequence=data.get("implementation_sequence", []),
                open_questions=data.get("open_questions", []),
                raw_hld=answer,
            )

        return HLDDraft(raw_hld=answer)

    def _run_align(
        self,
        prd: str,
        hld: HLDDraft,
    ) -> AlignmentReport:
        """Run Phase 4 alignment verification."""
        project = self._shesha.get_project(self._repos[0])
        prompt_template = self._load_prompt("align")

        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{hld}", hld.raw_hld)

        result = project.query(prompt)
        answer = result.answer

        data = self._extract_json(answer)

        if data:
            return AlignmentReport(
                covered=data.get("covered", []),
                gaps=data.get("gaps", []),
                scope_creep=data.get("scope_creep", []),
                alignment_score=float(data.get("alignment_score", 0.0)),
                recommendation=data.get("recommendation", "revise"),
                raw_analysis=answer,
            )

        return AlignmentReport(
            alignment_score=0.0,
            recommendation="revise",
            raw_analysis=answer,
        )

    def analyze(
        self,
        prd: str,
        on_discovery: Callable[[str], str | None] | None = None,
        on_alignment_issue: Callable[[AlignmentReport], str] | None = None,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> tuple[HLDDraft, AlignmentReport]:
        """Run the four-phase analysis.

        Args:
            prd: The PRD text (pasted inline).
            on_discovery: Called when new repo discovered.
                Receives repo hint (e.g. "auth-service"), returns URL to add
                (e.g. "https://github.com/org/auth-service") or None to skip.
                If None, discoveries are ignored.
            on_alignment_issue: Called if alignment finds problems.
                Receives report, returns "revise" | "accept" | "abort".
                If None, accepts as-is.
            on_progress: Called with (phase, message) updates.

        Returns:
            Tuple of (final HLD, alignment report).

        Raises:
            ValueError: If no repos have been added.
        """
        if not self._repos:
            raise ValueError("No repos added. Call add_repo() first.")

        # Phase 1: Recon
        if on_progress:
            on_progress("recon", f"Starting recon on {len(self._repos)} repos")

        for project_id in self._repos:
            if on_progress:
                on_progress("recon", f"Analyzing {project_id}")
            self._summaries[project_id] = self._run_recon(project_id)

        # Phase 2: Impact
        if on_progress:
            on_progress("impact", "Starting impact analysis")

        all_discovered: set[str] = set()  # Track all discoveries to avoid asking twice
        discovery_round = 0

        while discovery_round < self._max_discovery_rounds:
            repos_added_this_round = 0

            for project_id in self._repos:
                if project_id in self._impacts:
                    continue  # Already analyzed

                if on_progress:
                    on_progress("impact", f"Analyzing {project_id}")

                summary = self._summaries[project_id]
                report = self._run_impact(project_id, prd, summary)
                self._impacts[project_id] = report

                # Check for discoveries
                for dep in report.discovered_dependencies:
                    if dep not in self._repos and dep not in all_discovered:
                        all_discovered.add(dep)
                        if on_discovery:
                            url = on_discovery(dep)
                            if url:
                                # User provided URL - add the repo
                                if on_progress:
                                    on_progress("discovery", f"Adding discovered repo: {dep}")
                                new_project_id = self.add_repo(url)
                                if new_project_id:
                                    # Run recon on the new repo so it can be analyzed
                                    self._summaries[new_project_id] = self._run_recon(
                                        new_project_id
                                    )
                                    repos_added_this_round += 1

            discovery_round += 1
            # Only continue if new repos were added this round
            if repos_added_this_round == 0:
                break

        # Check context size before synthesis
        total_context_size = sum(len(report.raw_analysis) for report in self._impacts.values())
        if total_context_size > 500_000:  # 500KB warning threshold
            if on_progress:
                on_progress(
                    "synthesize",
                    f"Warning: Large context ({total_context_size:,} chars). "
                    "Consider reducing number of repos.",
                )

        # Phase 3: Synthesize
        if on_progress:
            on_progress("synthesize", "Generating HLD")

        hld = self._run_synthesize(prd, self._impacts)

        # Phase 4: Align
        if on_progress:
            on_progress("align", "Verifying alignment")

        alignment = self._run_align(prd, hld)

        # Handle alignment issues
        revision_round = 0
        while alignment.recommendation != "approved" and revision_round < self._max_revision_rounds:
            if on_alignment_issue:
                action = on_alignment_issue(alignment)
                if action == "accept":
                    break
                if action == "abort":
                    break
                # action == "revise" - continue loop
            else:
                break  # No callback, accept as-is

            revision_round += 1
            if on_progress:
                on_progress("synthesize", f"Revision round {revision_round}")

            hld = self._run_synthesize(prd, self._impacts, alignment_feedback=alignment)

            if on_progress:
                on_progress("align", "Re-verifying alignment")
            alignment = self._run_align(prd, hld)

        return hld, alignment
