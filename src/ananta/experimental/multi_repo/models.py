"""Data models for multi-repo PRD analysis."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepoSummary:
    """Output from Phase 1 recon query.

    Contains structural information about a repository:
    what it exposes and what it consumes.
    """

    project_id: str
    raw_summary: str
    apis: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ImpactReport:
    """Output from Phase 2 impact analysis.

    Describes how a PRD affects a specific repository
    and what other systems may need to be analyzed.
    """

    project_id: str
    affected: bool
    raw_analysis: str
    changes: list[str] = field(default_factory=list)
    new_interfaces: list[str] = field(default_factory=list)
    modified_interfaces: list[str] = field(default_factory=list)
    discovered_dependencies: list[str] = field(default_factory=list)


@dataclass
class HLDDraft:
    """Output from Phase 3 synthesis.

    A draft High-Level Design document covering changes
    across all analyzed repositories.
    """

    raw_hld: str
    component_changes: dict[str, list[str]] = field(default_factory=dict)
    data_flow: str = ""
    interface_contracts: list[str] = field(default_factory=list)
    implementation_sequence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class AlignmentReport:
    """Output from Phase 4 alignment verification.

    Validates that the HLD covers the PRD requirements
    without scope creep.
    """

    alignment_score: float
    recommendation: str  # "approved", "revise", "major_gaps"
    raw_analysis: str
    covered: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    scope_creep: list[dict[str, Any]] = field(default_factory=list)
