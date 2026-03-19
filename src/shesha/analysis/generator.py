"""Codebase analysis generator."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from shesha.models import (
    AnalysisComponent,
    AnalysisExternalDep,
    RepoAnalysis,
    coerce_to_str,
    coerce_to_str_list,
)

if TYPE_CHECKING:
    from shesha.project import Project


class AnalysisGenerator:
    """Generates codebase analysis using RLM queries."""

    def __init__(
        self,
        get_project: Callable[[str], "Project"],
        get_project_sha: Callable[[str], str | None],
    ) -> None:
        """Initialize the generator.

        Args:
            get_project: Callable that returns a Project for a given project ID.
            get_project_sha: Callable that returns the HEAD SHA for a project.
        """
        self._get_project = get_project
        self._get_project_sha = get_project_sha

    @property
    def get_project(self) -> Callable[[str], "Project"]:
        """The callable used to retrieve a Project by ID."""
        return self._get_project

    @property
    def get_project_sha(self) -> Callable[[str], str | None]:
        """The callable used to retrieve a project's HEAD SHA."""
        return self._get_project_sha

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from the prompts directory.

        Args:
            name: Name of the prompt file (without .md extension).

        Returns:
            The prompt content as a string.
        """
        prompts_dir = Path(__file__).parent / "prompts"
        return (prompts_dir / f"{name}.md").read_text()

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON object from text that may contain markdown.

        Note: Similar to MultiRepoAnalyzer._extract_json, but intentionally
        separate. The multi-repo version has a fast-path optimization for
        large responses. Keep both until a third call site justifies a
        shared utility.

        Args:
            text: Text that may contain JSON, possibly in markdown code blocks.

        Returns:
            Parsed JSON as a dict, or None if no valid JSON found.
        """
        # Try to find JSON in code blocks first
        json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return cast(dict[str, Any], json.loads(json_match.group(1)))
            except json.JSONDecodeError:
                pass  # Invalid JSON in code block, try raw extraction below

        # Try to find raw JSON
        start_idx = text.find("{")
        if start_idx != -1:
            for end_idx in range(len(text) - 1, start_idx, -1):
                if text[end_idx] == "}":
                    candidate = text[start_idx : end_idx + 1]
                    try:
                        return cast(dict[str, Any], json.loads(candidate))
                    except json.JSONDecodeError:
                        continue  # Not valid JSON, try shorter substring

        return None

    def generate(self, project_id: str) -> RepoAnalysis:
        """Generate a codebase analysis for a project.

        Args:
            project_id: The project to analyze.

        Returns:
            RepoAnalysis with the generated analysis.
        """
        project = self._get_project(project_id)
        prompt = self._load_prompt("generate")

        result = project.query(prompt)
        data = self._extract_json(result.answer)

        if data is None:
            data = {"overview": result.answer, "components": [], "external_dependencies": []}

        # Get current SHA
        head_sha = self._get_project_sha(project_id) or ""

        # Parse components
        components = []
        for c in data.get("components", []):
            components.append(
                AnalysisComponent(
                    name=coerce_to_str(c.get("name", "Unknown")),
                    path=coerce_to_str(c.get("path", "")),
                    description=coerce_to_str(c.get("description", "")),
                    apis=c.get("apis", []),
                    models=coerce_to_str_list(c.get("models", [])),
                    entry_points=coerce_to_str_list(c.get("entry_points", [])),
                    internal_dependencies=coerce_to_str_list(c.get("internal_dependencies", [])),
                    auth=c.get("auth"),
                    data_persistence=c.get("data_persistence"),
                )
            )

        # Parse external dependencies
        external_deps = []
        for d in data.get("external_dependencies", []):
            external_deps.append(
                AnalysisExternalDep(
                    name=coerce_to_str(d.get("name", "Unknown")),
                    type=coerce_to_str(d.get("type", "external_api")),
                    description=coerce_to_str(d.get("description", "")),
                    used_by=coerce_to_str_list(d.get("used_by", [])),
                    optional=d.get("optional", False),
                )
            )

        return RepoAnalysis(
            version="1",
            generated_at=datetime.now(UTC).isoformat(),
            head_sha=head_sha,
            overview=coerce_to_str(data.get("overview", "")),
            components=components,
            external_dependencies=external_deps,
        )
