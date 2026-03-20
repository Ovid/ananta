"""Tests for public API exports."""


def test_query_context_exported_from_ananta() -> None:
    """QueryContext is importable from ananta."""
    from ananta import QueryContext

    assert QueryContext is not None


def test_trace_writer_exported_from_rlm() -> None:
    """TraceWriter is importable from ananta.rlm."""
    from ananta.rlm import TraceWriter

    assert TraceWriter is not None


def test_project_info_exported() -> None:
    """ProjectInfo is exported from the public API."""
    from ananta import ProjectInfo

    assert ProjectInfo is not None
