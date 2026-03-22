"""Pydantic schemas for the arxiv web API.

Generic schemas are imported from ananta.explorers.shared_ui.schemas and
re-exported here.  Arxiv-specific schemas (PaperAdd, PaperInfo, SearchResult,
DownloadTaskStatus) are defined locally.
"""

from __future__ import annotations

from pydantic import BaseModel

# Re-export all shared schemas.
from ananta.explorers.shared_ui.schemas import (
    ContextBudget,
    ConversationHistory,
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

__all__ = [
    "ContextBudget",
    "ConversationHistory",
    "DownloadTaskStatus",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "PaperAdd",
    "PaperInfo",
    "PaperReorder",
    "PaperRename",
    "SearchResult",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
]


# Arxiv-only schemas


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


class PaperRename(BaseModel):
    new_name: str


class PaperReorder(BaseModel):
    arxiv_ids: list[str]


class DownloadTaskStatus(BaseModel):
    task_id: str
    papers: list[dict[str, str]]
