"""Pydantic schemas for the document explorer API.

Generic schemas are imported from shesha.experimental.shared.schemas and
re-exported here so that ``from document_explorer.schemas import X`` works for
all schema types.  Document-explorer-specific schemas (DocumentInfo,
DocumentUploadResponse) are defined locally.
"""

from __future__ import annotations

from pydantic import BaseModel

# Re-export shared schemas used by the document explorer API.
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


class DocumentRename(BaseModel):
    new_name: str


class DocumentUploadResponse(BaseModel):
    project_id: str
    filename: str
    status: str
