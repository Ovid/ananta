"""Pydantic schemas for the arxiv web API.

Generic schemas are imported from shesha.experimental.shared.schemas and
re-exported here for backward compatibility.  Arxiv-specific schemas
(PaperAdd, PaperInfo, SearchResult, DownloadTaskStatus) and arxiv-flavoured
overrides (TopicInfo with paper_count, ExchangeSchema with paper_ids) are
defined locally.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

# Re-export generic schemas so existing ``from web.schemas import X`` still works.
from shesha.experimental.shared.schemas import (
    ContextBudget,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)

# Ensure re-exports are visible to star-imports and static analysis.
__all__ = [
    "ContextBudget",
    "ConversationHistory",
    "DownloadTaskStatus",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "PaperAdd",
    "PaperInfo",
    "SearchResult",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
]


# ---------------------------------------------------------------------------
# Arxiv-specific overrides of shared schemas
# ---------------------------------------------------------------------------


class TopicInfo(BaseModel):
    """Arxiv-flavoured TopicInfo using ``paper_count`` instead of the shared
    schema's ``document_count``."""

    name: str
    paper_count: int
    size: str
    project_id: str


class ExchangeSchema(BaseModel):
    """Arxiv-flavoured ExchangeSchema using ``paper_ids`` instead of the shared
    schema's ``document_ids``.

    The shared session stores consulted IDs under ``document_ids``.  The
    ``validation_alias`` lets Pydantic accept either name when constructing
    the model (e.g. from ``session.list_exchanges()`` dicts), while
    ``serialization_alias`` ensures the REST response uses ``paper_ids``.
    """

    model_config = {"populate_by_name": True}

    exchange_id: str
    question: str
    answer: str
    trace_id: str | None = None
    timestamp: str
    tokens: dict[str, int]
    execution_time: float
    model: str
    paper_ids: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("paper_ids", "document_ids"),
        serialization_alias="paper_ids",
    )


class ConversationHistory(BaseModel):
    """Local override so exchanges are validated with the arxiv-flavoured
    ``ExchangeSchema`` (which carries ``paper_ids``, not ``document_ids``).
    Using the shared ``ConversationHistory`` would silently drop ``paper_ids``
    during Pydantic v2 validation."""

    exchanges: list[ExchangeSchema]


# ---------------------------------------------------------------------------
# Arxiv-only schemas (no shared equivalent)
# ---------------------------------------------------------------------------


class PaperAdd(BaseModel):
    arxiv_id: str
    topics: list[str]


class PaperInfo(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    source_type: str | None = None


class SearchResult(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    in_topics: list[str] = []


class DownloadTaskStatus(BaseModel):
    task_id: str
    papers: list[dict[str, str]]
