"""Generic Pydantic schemas for the web API.

Domain-specific schemas (e.g. arxiv paper models) live in their
respective tool modules; these schemas are shared across all tools.
"""

from __future__ import annotations

from pydantic import BaseModel


class ItemReorder(BaseModel):
    item_ids: list[str]


class TopicCreate(BaseModel):
    name: str


class TopicRename(BaseModel):
    new_name: str


class TopicInfo(BaseModel):
    name: str
    document_count: int
    size: str
    project_id: str


class TraceStepSchema(BaseModel):
    step_type: str
    iteration: int
    content: str
    timestamp: str
    tokens_used: int | None = None
    duration_ms: int | None = None


class TraceListItem(BaseModel):
    trace_id: str
    question: str
    timestamp: str
    status: str
    total_tokens: int
    duration_ms: int


class TraceFull(BaseModel):
    trace_id: str
    question: str
    model: str
    timestamp: str
    steps: list[TraceStepSchema]
    total_tokens: dict[str, int]
    total_iterations: int
    duration_ms: int
    status: str
    document_ids: list[str] = []


class ExchangeSchema(BaseModel):
    exchange_id: str
    question: str
    answer: str
    trace_id: str | None = None
    timestamp: str
    tokens: dict[str, int]
    execution_time: float
    model: str
    document_ids: list[str] | None = None
    allow_background_knowledge: bool = False
    gave_up: bool = False


class ConversationHistory(BaseModel):
    exchanges: list[ExchangeSchema]


class ModelInfo(BaseModel):
    model: str
    max_input_tokens: int | None = None


class ModelUpdate(BaseModel):
    model: str


class ContextBudget(BaseModel):
    used_tokens: int
    max_tokens: int
    percentage: float
    level: str  # "green", "amber", "red"
