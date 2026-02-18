"""Verify arxiv schemas use standardized field names."""

from shesha.experimental.shared.schemas import ExchangeSchema, TopicInfo


def test_topic_info_uses_document_count() -> None:
    """TopicInfo from shared schemas has document_count, not paper_count."""
    info = TopicInfo(name="test", document_count=5, size="1 MB", project_id="p1")
    assert info.document_count == 5
    assert not hasattr(info, "paper_count")


def test_exchange_schema_uses_document_ids() -> None:
    """ExchangeSchema from shared schemas has document_ids, not paper_ids."""
    ex = ExchangeSchema(
        exchange_id="e1",
        question="q",
        answer="a",
        timestamp="2026-01-01",
        tokens={"prompt": 1, "completion": 1, "total": 2},
        execution_time=0.5,
        model="test",
        document_ids=["d1"],
    )
    assert ex.document_ids == ["d1"]
    assert not hasattr(ex, "paper_ids")


def test_web_schemas_reexport_shared_topic_info() -> None:
    """web.schemas.TopicInfo should be the shared version (document_count)."""
    from shesha.experimental.web.schemas import TopicInfo as WebTopicInfo

    info = WebTopicInfo(name="test", document_count=5, size="1 MB", project_id="p1")
    assert info.document_count == 5


def test_web_schemas_reexport_shared_exchange() -> None:
    """web.schemas.ExchangeSchema should be the shared version (document_ids)."""
    from shesha.experimental.web.schemas import ExchangeSchema as WebExchange

    ex = WebExchange(
        exchange_id="e1",
        question="q",
        answer="a",
        timestamp="2026-01-01",
        tokens={"prompt": 1, "completion": 1, "total": 2},
        execution_time=0.5,
        model="test",
        document_ids=["d1"],
    )
    assert ex.document_ids == ["d1"]
