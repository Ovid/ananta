"""Tests for document explorer Pydantic schemas."""

from __future__ import annotations

import pydantic
import pytest

from ananta.experimental.document_explorer.schemas import (
    ContextBudget,
    DocumentInfo,
    DocumentUploadResponse,
    ExchangeSchema,
    ModelInfo,
    TopicCreate,
    TopicInfo,
    TopicRename,
)


class TestDocumentInfo:
    def test_all_fields(self) -> None:
        d = DocumentInfo(
            project_id="quarterly-report-a3f2",
            filename="Quarterly Report.pdf",
            content_type="application/pdf",
            size=102400,
            upload_date="2026-03-05T12:00:00Z",
            page_count=15,
        )
        assert d.project_id == "quarterly-report-a3f2"
        assert d.filename == "Quarterly Report.pdf"
        assert d.size == 102400
        assert d.page_count == 15

    def test_page_count_nullable(self) -> None:
        d = DocumentInfo(
            project_id="notes-b1c2",
            filename="notes.txt",
            content_type="text/plain",
            size=256,
            upload_date="2026-03-05T12:00:00Z",
            page_count=None,
        )
        assert d.page_count is None

    def test_requires_fields(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            DocumentInfo(project_id="x")  # type: ignore[call-arg]


class TestDocumentUploadResponse:
    def test_all_fields(self) -> None:
        r = DocumentUploadResponse(
            project_id="doc-abc-1234",
            filename="report.pdf",
            status="created",
        )
        assert r.project_id == "doc-abc-1234"
        assert r.status == "created"


class TestReexportedSharedSchemas:
    def test_topic_create(self) -> None:
        t = TopicCreate(name="Research")
        assert t.name == "Research"

    def test_topic_rename(self) -> None:
        t = TopicRename(new_name="New Name")
        assert t.new_name == "New Name"

    def test_topic_info(self) -> None:
        t = TopicInfo(
            name="Research",
            document_count=5,
            size="",
            project_id="topic:Research",
        )
        assert t.document_count == 5

    def test_exchange_schema(self) -> None:
        e = ExchangeSchema(
            exchange_id="uuid-1",
            question="What?",
            answer="That.",
            timestamp="2026-03-05T12:00:00Z",
            tokens={"prompt": 100, "completion": 50, "total": 150},
            execution_time=5.0,
            model="test",
            document_ids=["doc-1"],
        )
        assert e.document_ids == ["doc-1"]

    def test_model_info(self) -> None:
        m = ModelInfo(model="test", max_input_tokens=128000)
        assert m.model == "test"

    def test_context_budget(self) -> None:
        b = ContextBudget(used_tokens=1000, max_tokens=128000, percentage=0.8, level="green")
        assert b.level == "green"
