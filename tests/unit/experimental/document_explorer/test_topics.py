"""Tests for DocumentTopicManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shesha.experimental.document_explorer.topics import DocumentTopicManager


class TestCreateAndListTopics:
    def test_create_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        assert "Reports" in mgr.list_topics()

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        assert mgr.list_topics() == []

    def test_list_topics_multiple(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Contracts")
        mgr.create("Research")
        assert sorted(mgr.list_topics()) == ["Contracts", "Reports", "Research"]

    def test_topic_json_metadata(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("My Docs")
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        meta = json.loads((dirs[0] / "topic.json").read_text())
        assert meta["name"] == "My Docs"
        assert meta["docs"] == []

    def test_create_duplicate_is_idempotent(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Reports")
        assert mgr.list_topics().count("Reports") == 1

    @pytest.mark.parametrize("name", ["!!!", "   ", "---", ""])
    def test_create_rejects_empty_slug(self, tmp_path: Path, name: str) -> None:
        mgr = DocumentTopicManager(tmp_path)
        with pytest.raises(ValueError, match="[Ee]mpty"):
            mgr.create(name)


class TestAddAndListDocs:
    def test_add_doc_to_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "quarterly-report-a3f2")
        assert mgr.list_docs("Reports") == ["quarterly-report-a3f2"]

    def test_add_multiple_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-2")
        assert sorted(mgr.list_docs("Reports")) == ["doc-1", "doc-2"]

    def test_list_docs_empty_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.list_docs("Empty") == []

    def test_add_duplicate_doc_is_idempotent(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-1")
        assert mgr.list_docs("Reports") == ["doc-1"]

    def test_add_doc_to_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.add_doc("Nonexistent", "doc-1")


class TestRemoveDoc:
    def test_remove_doc_from_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_doc("Reports", "doc-1")
        mgr.add_doc("Reports", "doc-2")
        mgr.remove_doc("Reports", "doc-1")
        assert mgr.list_docs("Reports") == ["doc-2"]

    def test_remove_nonexistent_doc_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        with pytest.raises(ValueError, match="Doc not found"):
            mgr.remove_doc("Reports", "nonexistent")


class TestSameDocMultipleTopics:
    def test_same_doc_in_multiple_topics(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Research")
        mgr.add_doc("Reports", "shared-doc")
        mgr.add_doc("Research", "shared-doc")
        assert "shared-doc" in mgr.list_docs("Reports")
        assert "shared-doc" in mgr.list_docs("Research")


class TestListAllDocs:
    def test_list_all_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "doc-1")
        mgr.add_doc("A", "doc-2")
        mgr.add_doc("B", "doc-2")
        mgr.add_doc("B", "doc-3")
        assert sorted(mgr.list_all_docs()) == ["doc-1", "doc-2", "doc-3"]

    def test_list_all_docs_no_duplicates(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        assert mgr.list_all_docs() == ["shared"]


class TestUncategorizedDocs:
    def test_list_uncategorized_docs(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.add_doc("A", "doc-1")
        uncategorized = mgr.list_uncategorized_docs(["doc-1", "doc-2", "doc-3"])
        assert sorted(uncategorized) == ["doc-2", "doc-3"]


class TestDeleteTopic:
    def test_delete_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("ToDelete")
        mgr.delete("ToDelete")
        assert mgr.list_topics() == []


class TestFindTopicsForDoc:
    def test_find_topics_for_doc(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        assert sorted(mgr.find_topics_for_doc("shared")) == ["A", "B"]


class TestRemoveDocFromAll:
    def test_remove_doc_from_all(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_doc("A", "shared")
        mgr.add_doc("B", "shared")
        mgr.add_doc("B", "other")
        mgr.remove_doc_from_all("shared")
        assert mgr.list_docs("A") == []
        assert mgr.list_docs("B") == ["other"]


class TestGetTopicDir:
    def test_returns_topic_directory(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Reports")
        topic_dir = mgr.get_topic_dir("Reports")
        assert topic_dir.is_dir()
        meta = json.loads((topic_dir / "topic.json").read_text())
        assert meta["name"] == "Reports"

    def test_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.get_topic_dir("Nonexistent")


class TestRenameTopic:
    def test_rename_topic(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Old")
        mgr.add_doc("Old", "doc-1")
        mgr.rename("Old", "New")
        assert "New" in mgr.list_topics()
        assert "Old" not in mgr.list_topics()
        assert mgr.list_docs("New") == ["doc-1"]

    def test_rename_to_existing_raises(self, tmp_path: Path) -> None:
        mgr = DocumentTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.create("Beta")
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("Alpha", "Beta")
