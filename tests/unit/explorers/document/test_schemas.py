"""Tests for document explorer Pydantic schemas."""

from __future__ import annotations

import pydantic
import pytest

from ananta.explorers.document.schemas import (
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


def test_document_info_accepts_relative_path_and_session_id():
    info = DocumentInfo(
        project_id="x-12345678",
        filename="README.md",
        content_type="text/markdown",
        size=42,
        upload_date="2026-05-05T00:00:00Z",
        page_count=None,
        relative_path="docs/api/README.md",
        upload_session_id="11111111-1111-1111-1111-111111111111",
    )
    assert info.relative_path == "docs/api/README.md"
    assert info.upload_session_id == "11111111-1111-1111-1111-111111111111"


def test_document_info_relative_path_optional():
    info = DocumentInfo(
        project_id="x-12345678",
        filename="README.md",
        content_type="text/markdown",
        size=42,
        upload_date="2026-05-05T00:00:00Z",
        page_count=None,
    )
    assert info.relative_path is None
    assert info.upload_session_id is None


class TestDocumentUploadResponse:
    def test_all_fields(self) -> None:
        r = DocumentUploadResponse(
            project_id="doc-abc-1234",
            filename="report.pdf",
            status="created",
        )
        assert r.project_id == "doc-abc-1234"
        assert r.status == "created"


def test_document_upload_response_status_and_reason():
    ok = DocumentUploadResponse(
        project_id="x-12345678",
        filename="a.md",
        status="created",
    )
    assert ok.reason is None

    failed = DocumentUploadResponse(
        project_id="",
        filename="bad.pdf",
        status="failed",
        reason="text extraction failed: corrupt PDF",
    )
    assert failed.status == "failed"
    assert failed.reason == "text extraction failed: corrupt PDF"


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
