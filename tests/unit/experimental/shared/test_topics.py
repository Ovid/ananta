"""Tests for BaseTopicManager."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from shesha.experimental.shared.topics import BaseTopicManager, _slugify

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class TestSlugify:
    """_slugify output must match _SAFE_ID_RE so generated IDs are API-valid."""

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("hello world", "hello-world"),
            ("My Report", "my-report"),
            ("file_name", "file-name"),
            ("a--b", "a-b"),
        ],
    )
    def test_basic_slugs(self, input_text: str, expected: str) -> None:
        assert _slugify(input_text) == expected

    @pytest.mark.parametrize(
        "input_text",
        ["résumé", "über", "café_report", "naïve-analysis"],
    )
    def test_unicode_slugs_match_safe_id(self, input_text: str) -> None:
        slug = _slugify(input_text)
        assert slug, f"_slugify({input_text!r}) returned empty string"
        assert _SAFE_ID_RE.match(slug), (
            f"_slugify({input_text!r}) = {slug!r} does not match _SAFE_ID_RE"
        )

    def test_pure_non_latin_returns_empty(self) -> None:
        assert _slugify("日本語") == ""

    def test_mixed_ascii_and_cjk_keeps_ascii_part(self) -> None:
        slug = _slugify("report-日本語-2024")
        assert _SAFE_ID_RE.match(slug), f"{slug!r} does not match _SAFE_ID_RE"
        assert "report" in slug


class TestCorruptMetaHandling:
    """Corrupt or partially-written topic.json should not crash callers."""

    def test_missing_name_key_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"items": ["a"]}')
        assert mgr.list_topics() == []

    def test_missing_items_key_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": "Reports"}')
        assert mgr.list_topics() == []

    def test_wrong_type_name_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": 42, "items": []}')
        assert mgr.list_topics() == []

    def test_wrong_type_items_treated_as_corrupt(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        topic_dir = tmp_path / "broken"
        topic_dir.mkdir()
        (topic_dir / "topic.json").write_text('{"name": "Reports", "items": "not-a-list"}')
        assert mgr.list_topics() == []

    def test_valid_topics_unaffected_by_corrupt_sibling(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Good")
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()
        (broken_dir / "topic.json").write_text("{bad json")
        assert mgr.list_topics() == ["Good"]


class TestCreateAndListTopics:
    def test_create_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        assert "Reports" in mgr.list_topics()

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        assert mgr.list_topics() == []

    def test_list_topics_multiple(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Contracts")
        mgr.create("Research")
        assert sorted(mgr.list_topics()) == ["Contracts", "Reports", "Research"]

    def test_topic_json_uses_items_key(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("My Docs")
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        meta = json.loads((dirs[0] / "topic.json").read_text())
        assert meta["name"] == "My Docs"
        assert meta["items"] == []

    def test_create_duplicate_is_idempotent(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Reports")
        assert mgr.list_topics().count("Reports") == 1

    @pytest.mark.parametrize("name", ["!!!", "   ", "---", ""])
    def test_create_rejects_empty_slug(self, tmp_path: Path, name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="[Ee]mpty"):
            mgr.create(name)

    @pytest.mark.parametrize("name", ["foo/bar", "a\\b", "x/y/z"])
    def test_create_rejects_path_separators(self, tmp_path: Path, name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="path separator"):
            mgr.create(name)

    def test_create_slug_collision_different_name_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Research")
        with pytest.raises(ValueError, match="different display name"):
            mgr.create("research")

    def test_create_recovers_corrupt_topic_json(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Research")
        topic_dir = mgr.get_topic_dir("Research")
        (topic_dir / "topic.json").write_text("not valid json")
        mgr.create("Research")
        assert "Research" in mgr.list_topics()


class TestAddAndListItems:
    def test_add_item_to_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "quarterly-report-a3f2")
        assert mgr.list_items("Reports") == ["quarterly-report-a3f2"]

    def test_add_multiple_items(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-2")
        assert sorted(mgr.list_items("Reports")) == ["item-1", "item-2"]

    def test_list_items_empty_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.list_items("Empty") == []

    def test_add_duplicate_item_is_idempotent(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-1")
        assert mgr.list_items("Reports") == ["item-1"]

    def test_add_item_to_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.add_item("Nonexistent", "item-1")


class TestRemoveItem:
    def test_remove_item_from_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "item-1")
        mgr.add_item("Reports", "item-2")
        mgr.remove_item("Reports", "item-1")
        assert mgr.list_items("Reports") == ["item-2"]

    def test_remove_nonexistent_item_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        with pytest.raises(ValueError, match="Item not found"):
            mgr.remove_item("Reports", "nonexistent")


class TestSameItemMultipleTopics:
    def test_same_item_in_multiple_topics(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.create("Research")
        mgr.add_item("Reports", "shared-item")
        mgr.add_item("Research", "shared-item")
        assert "shared-item" in mgr.list_items("Reports")
        assert "shared-item" in mgr.list_items("Research")


class TestListAllItems:
    def test_list_all_items(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "item-1")
        mgr.add_item("A", "item-2")
        mgr.add_item("B", "item-2")
        mgr.add_item("B", "item-3")
        assert sorted(mgr.list_all_items()) == ["item-1", "item-2", "item-3"]

    def test_list_all_items_no_duplicates(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        assert mgr.list_all_items() == ["shared"]


class TestUncategorized:
    def test_list_uncategorized(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.add_item("A", "item-1")
        uncategorized = mgr.list_uncategorized(["item-1", "item-2", "item-3"])
        assert sorted(uncategorized) == ["item-2", "item-3"]


class TestDeleteTopic:
    def test_delete_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("ToDelete")
        mgr.delete("ToDelete")
        assert mgr.list_topics() == []


class TestFindTopicsForItem:
    def test_find_topics_for_item(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        assert sorted(mgr.find_topics_for_item("shared")) == ["A", "B"]


class TestRemoveItemFromAll:
    def test_remove_item_from_all(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.add_item("A", "shared")
        mgr.add_item("B", "shared")
        mgr.add_item("B", "other")
        mgr.remove_item_from_all("shared")
        assert mgr.list_items("A") == []
        assert mgr.list_items("B") == ["other"]


class TestGetTopicDir:
    def test_returns_topic_directory(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        topic_dir = mgr.get_topic_dir("Reports")
        assert topic_dir.is_dir()
        meta = json.loads((topic_dir / "topic.json").read_text())
        assert meta["name"] == "Reports"

    def test_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.get_topic_dir("Nonexistent")


class TestRenameTopic:
    def test_rename_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Old")
        mgr.add_item("Old", "item-1")
        mgr.rename("Old", "New")
        assert "New" in mgr.list_topics()
        assert "Old" not in mgr.list_topics()
        assert mgr.list_items("New") == ["item-1"]

    def test_rename_to_existing_raises(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.create("Beta")
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("Alpha", "Beta")

    @pytest.mark.parametrize("new_name", ["foo/bar", "a\\b"])
    def test_rename_rejects_path_separators(self, tmp_path: Path, new_name: str) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Safe")
        with pytest.raises(ValueError, match="path separator"):
            mgr.rename("Safe", new_name)
