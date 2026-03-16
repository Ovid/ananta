"""Smoke tests for DocumentTopicManager subclass.

Full coverage lives in tests/unit/experimental/shared/test_topics.py.
"""

from pathlib import Path

from shesha.experimental.document_explorer.topics import DocumentTopicManager


class TestDocumentTopicManagerSubclass:
    def test_is_usable(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Test")
        assert mgr.list_topics() == ["Test"]
