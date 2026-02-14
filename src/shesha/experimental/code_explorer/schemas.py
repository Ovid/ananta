"""Pydantic schemas for the code explorer API.

Generic schemas are imported from shesha.experimental.shared.schemas and
re-exported here so that ``from code_explorer.schemas import X`` works for
all schema types.  Unlike the arxiv explorer, the code explorer uses the
shared TopicInfo (with ``document_count``) and ExchangeSchema (with
``document_ids``) directly -- no domain-specific overrides are needed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Re-export shared schemas used by the code explorer API.
from shesha.experimental.shared.schemas import (
    ContextBudget,
    ExchangeSchema,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)

# Ensure re-exports are visible to star-imports and static analysis.
__all__ = [
    "AnalysisResponse",
    "ContextBudget",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "RepoAdd",
    "RepoInfo",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
    "UpdateStatus",
]


# ---------------------------------------------------------------------------
# Code-explorer-specific schemas
# ---------------------------------------------------------------------------


class RepoAdd(BaseModel):
    url: str
    topic: str | None = None


class RepoInfo(BaseModel):
    project_id: str
    source_url: str
    file_count: int
    analysis_status: str | None  # "current", "stale", "missing"


class AnalysisResponse(BaseModel):
    version: str
    generated_at: str
    head_sha: str
    overview: str
    components: list[dict[str, Any]]
    external_dependencies: list[dict[str, Any]]
    caveats: str


class UpdateStatus(BaseModel):
    status: str  # "unchanged", "updates_available"
    files_ingested: int
