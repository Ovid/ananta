"""Pydantic schemas for the document explorer API.

Generic schemas are imported from ananta.explorers.shared_ui.schemas and
re-exported here so that ``from document_explorer.schemas import X`` works for
all schema types.  Document-explorer-specific schemas (DocumentInfo,
DocumentUploadResponse) are defined locally.
"""

from __future__ import annotations

from pydantic import BaseModel

# Re-export shared schemas used by the document explorer API.
from ananta.explorers.shared_ui.schemas import (
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
    "ContextBudget",
    "DocumentInfo",
    "DocumentRename",
    "DocumentUploadResponse",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
]


# ---------------------------------------------------------------------------
# Document-explorer-specific schemas
# ---------------------------------------------------------------------------


class DocumentInfo(BaseModel):
    project_id: str
    filename: str
    content_type: str
    size: int
    upload_date: str
    page_count: int | None
    relative_path: str | None = None
    upload_session_id: str | None = None


class DocumentRename(BaseModel):
    new_name: str


class DocumentUploadResponse(BaseModel):
    project_id: str
    filename: str
    status: str
