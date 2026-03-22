"""Smoke tests for CodeExplorerTopicManager subclass.

Full coverage lives in tests/unit/explorers/shared_ui/test_topics.py.
"""

from pathlib import Path

from ananta.explorers.code.topics import CodeExplorerTopicManager


class TestCodeExplorerTopicManagerSubclass:
    def test_is_usable(self, tmp_path: Path) -> None:
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Test")
        assert mgr.list_topics() == ["Test"]
