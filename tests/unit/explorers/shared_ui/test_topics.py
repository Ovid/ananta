"""Tests for BaseTopicManager."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ananta.explorers.shared_ui.topics import BaseTopicManager, _slugify

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

    def test_create_existing_topic_is_idempotent(self, tmp_path: Path) -> None:
        """Regression guard (Task A5): re-creating an existing topic must not raise.

        The folder-upload flow relies on this — every uploaded file calls
        ``topic_mgr.create(topic)`` regardless of whether the topic already
        exists. If this contract regresses, single-file and folder uploads to
        an existing topic both break.
        """
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Barsoom")
        mgr.create("Barsoom")  # must not raise
        assert "Barsoom" in mgr.list_topics()
        # No duplicates either: idempotent means at most one entry.
        assert mgr.list_topics().count("Barsoom") == 1

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

    def test_create_rejects_overlong_name(self, tmp_path: Path) -> None:
        """Topic names above the length cap are rejected (I5).

        Without a cap, a hostile direct API caller could submit a multi-MB
        topic name that gets stored verbatim in topic.json (disk-fill /
        topic-store bloat) and rendered into the UI sidebar (layout break).
        The 256 MiB body cap is too coarse for what is meaningfully a
        human-readable label.
        """
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="too long"):
            mgr.create("x" * 300)

    @pytest.mark.parametrize("name", ["bad\x00name", "tab\there", "newline\nhere", "del\x7fchar"])
    def test_create_rejects_control_bytes(self, tmp_path: Path, name: str) -> None:
        """Control bytes in topic names are rejected (I5).

        NUL/CR/LF in stored topic.json values can break consumers that read
        them as line-oriented files, and rendering them in the UI sidebar
        can cause unexpected layout effects.
        """
        mgr = BaseTopicManager(tmp_path)
        with pytest.raises(ValueError, match="control"):
            mgr.create(name)

    def test_create_strips_surrounding_whitespace(self, tmp_path: Path) -> None:
        """Whitespace around topic names is stripped on create (I12).

        rename_document strips, but upload_documents previously did not. The
        same display name with and without trailing whitespace produced two
        topics that slugified to the same directory but had different stored
        names — _resolve matched names exactly, so subsequent add_item calls
        failed to find the topic. Normalize whitespace at every entry point.
        """
        mgr = BaseTopicManager(tmp_path)
        mgr.create("  Reports  ")
        # The stored display name has no surrounding whitespace.
        assert mgr.list_topics() == ["Reports"]
        # add_item with the trimmed form must resolve to the same topic.
        mgr.add_item("Reports", "project-1")
        assert mgr.list_items("Reports") == ["project-1"]
        # Re-creating with whitespace is idempotent (same name after strip).
        mgr.create("Reports")
        assert mgr.list_topics() == ["Reports"]

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


class TestResolve:
    """I6: BaseTopicManager must provide resolve() for shared routes/websockets."""

    def test_resolve_returns_first_item(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        mgr.add_item("Reports", "proj-1")
        mgr.add_item("Reports", "proj-2")
        assert mgr.resolve("Reports") == "proj-1"

    def test_resolve_returns_none_for_missing_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        assert mgr.resolve("nonexistent") is None

    def test_resolve_returns_none_for_empty_topic(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.resolve("Empty") is None


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

    def test_rename_rejects_collision_with_corrupt_sibling_slug(self, tmp_path: Path) -> None:
        """Rename must reject a target whose slug matches a corrupt sibling's
        directory (S17).

        ``rename``'s duplicate-name check skipped corrupt-meta siblings
        (``_read_meta`` returns None). If a topic dir exists at the slug
        that ``new_name`` would map to, we cannot tell from the corrupt
        meta whether that sibling already carries ``new_name`` — so the
        rename succeeds, and if the corrupt meta is later repaired via
        ``create(new_name)`` we'd end up with two topics sharing the same
        display name (soft data corruption).

        Conservative fix: check directory slugs too, so a corrupt sibling
        squatting on the rename target's slug blocks the rename.
        """
        mgr = BaseTopicManager(tmp_path)
        # Two topics: A (will be corrupted) and B (we will try to rename).
        mgr.create("A")
        mgr.create("B")
        # Corrupt A's topic.json so _read_meta returns None.
        a_dir = mgr.get_topic_dir("A")
        (a_dir / "topic.json").write_text("not valid json")
        # Renaming B → "A" must be rejected — A's slug is occupied by a
        # sibling we can't introspect, and silently allowing the rename
        # would later produce two topics named "A" if A's meta is repaired.
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("B", "A")

    @pytest.mark.parametrize("new_name", ["", "   ", "\t", "  \n  "])
    def test_rename_rejects_whitespace_only(self, tmp_path: Path, new_name: str) -> None:
        """``rename`` rejects empty or whitespace-only names (I4).

        ``_normalize_name`` strips whitespace before validation. Without
        an empty-after-strip check in ``_validate_name``, ``rename(old,
        "   ")`` slipped through and wrote ``meta["name"] = ""``,
        leaving the topic on disk behind a label-less, unselectable row
        in the sidebar — soft data corruption: the topic exists but
        cannot be reached through the UI.

        ``create`` already rejects empty names downstream (via the empty-
        slug check), so this test pins the rename path to the same
        contract via the shared validator.
        """
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        with pytest.raises(ValueError, match="empty|whitespace"):
            mgr.rename("Reports", new_name)
        # The topic must still be findable under its original name.
        assert "Reports" in mgr.list_topics()


class TestReorderItems:
    @pytest.fixture
    def mgr(self, tmp_path: Path) -> BaseTopicManager:
        return BaseTopicManager(tmp_path)

    def test_reorder_changes_item_order(self, mgr: BaseTopicManager) -> None:
        mgr.create("Alpha")
        mgr.add_item("Alpha", "a")
        mgr.add_item("Alpha", "b")
        mgr.add_item("Alpha", "c")
        mgr.reorder_items("Alpha", ["c", "a", "b"])
        assert mgr.list_items("Alpha") == ["c", "a", "b"]

    def test_reorder_nonexistent_topic_raises(self, mgr: BaseTopicManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            mgr.reorder_items("NoSuch", ["a"])

    def test_reorder_with_mismatched_ids_raises(self, mgr: BaseTopicManager) -> None:
        mgr.create("Alpha")
        mgr.add_item("Alpha", "a")
        mgr.add_item("Alpha", "b")
        with pytest.raises(ValueError, match="must contain exactly"):
            mgr.reorder_items("Alpha", ["a", "b", "c"])

    def test_reorder_with_missing_ids_raises(self, mgr: BaseTopicManager) -> None:
        mgr.create("Alpha")
        mgr.add_item("Alpha", "a")
        mgr.add_item("Alpha", "b")
        with pytest.raises(ValueError, match="must contain exactly"):
            mgr.reorder_items("Alpha", ["a"])

    def test_reorder_preserves_topic_name(self, mgr: BaseTopicManager) -> None:
        mgr.create("Alpha")
        mgr.add_item("Alpha", "a")
        mgr.add_item("Alpha", "b")
        mgr.reorder_items("Alpha", ["b", "a"])
        # Topic name should be unchanged
        assert "Alpha" in mgr.list_topics()


class TestConcurrentMutation:
    """Mutating methods are read-modify-write on topic.json. Without a lock,
    two thread-pool workers servicing concurrent uploads to the same topic
    can interleave: A reads ``[X]``, B reads ``[X]``, A writes ``[X, Y]``,
    B writes ``[X, Z]`` — Y is lost. The recent move of ``_persist_one_upload``
    into ``asyncio.to_thread`` makes this race meaningfully reachable for
    parallel folder uploads to the same topic (I2).
    """

    def test_concurrent_add_item_does_not_lose_writes(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")

        n = 50
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(mgr.add_item, "Reports", f"item-{i}") for i in range(n)]
            for f in futures:
                f.result()

        items = mgr.list_items("Reports")
        assert len(items) == n
        assert sorted(items) == sorted(f"item-{i}" for i in range(n))

    def test_concurrent_remove_item_does_not_resurrect_others(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        n = 50
        for i in range(n):
            mgr.add_item("Reports", f"item-{i}")

        # Remove the first half concurrently. Without a lock, an interleave
        # where T_remove(item-0) reads [0..49] but T_remove(item-1)'s write
        # of [0,2..49] lands first will see T_remove(item-0) write [1..49] —
        # resurrecting item-1.
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [
                pool.submit(mgr.remove_item, "Reports", f"item-{i}") for i in range(n // 2)
            ]
            for f in futures:
                f.result()

        items = mgr.list_items("Reports")
        assert sorted(items) == sorted(f"item-{i}" for i in range(n // 2, n))

    def test_concurrent_remove_item_from_all_drops_every_ref(self, tmp_path: Path) -> None:
        mgr = BaseTopicManager(tmp_path)
        mgr.create("Reports")
        n = 50
        for i in range(n):
            mgr.add_item("Reports", f"item-{i}")

        # Issue 50 concurrent remove_item_from_all calls; each removes a
        # different item. All should be gone afterwards.
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [
                pool.submit(mgr.remove_item_from_all, f"item-{i}") for i in range(n)
            ]
            for f in futures:
                f.result()

        assert mgr.list_items("Reports") == []
