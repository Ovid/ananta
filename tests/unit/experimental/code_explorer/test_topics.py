"""Tests for CodeExplorerTopicManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager


class TestCreateAndListTopics:
    """Tests for creating and listing topics."""

    def test_create_topic(self, tmp_path: Path) -> None:
        """Creating a topic creates a directory with topic.json."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        topics = mgr.list_topics()
        assert "Frontend" in topics

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        """Listing topics on an empty directory returns empty list."""
        mgr = CodeExplorerTopicManager(tmp_path)
        assert mgr.list_topics() == []

    def test_list_topics_multiple(self, tmp_path: Path) -> None:
        """Listing topics returns all created topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.create("DevOps")
        topics = mgr.list_topics()
        assert sorted(topics) == ["Backend", "DevOps", "Frontend"]

    def test_topic_json_metadata(self, tmp_path: Path) -> None:
        """Topic metadata is stored as topic.json (no leading underscore)."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("My Topic")

        # Find the topic directory
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        meta_path = dirs[0] / "topic.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["name"] == "My Topic"
        assert meta["repos"] == []

    def test_topic_directory_is_slugified(self, tmp_path: Path) -> None:
        """Topic directory name is a slugified version of the name."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("My Cool Topic!")
        dirs = [d.name for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        assert dirs[0] == "my-cool-topic"

    def test_create_duplicate_topic_is_idempotent(self, tmp_path: Path) -> None:
        """Creating a topic that already exists does not raise or duplicate."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Frontend")
        topics = mgr.list_topics()
        assert topics.count("Frontend") == 1

    @pytest.mark.parametrize("name", ["!!!", "   ", "---", ""])
    def test_create_rejects_empty_slug(self, tmp_path: Path, name: str) -> None:
        """Names that slugify to empty string are rejected, not silently
        mapped to the topics root directory."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="[Ee]mpty"):
            mgr.create(name)

    @pytest.mark.parametrize("name", ["foo/bar", "a\\b", "x/y/z"])
    def test_create_rejects_path_separators(self, tmp_path: Path, name: str) -> None:
        """Names containing path separators are rejected."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="path separator"):
            mgr.create(name)


class TestAddAndListRepos:
    """Tests for adding repos to topics and listing them."""

    def test_add_repo_to_topic(self, tmp_path: Path) -> None:
        """Adding a repo to a topic makes it appear in list_repos."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.add_repo("Frontend", "project-abc-123")
        repos = mgr.list_repos("Frontend")
        assert repos == ["project-abc-123"]

    def test_add_multiple_repos(self, tmp_path: Path) -> None:
        """Adding multiple repos to a topic lists them all."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Backend")
        mgr.add_repo("Backend", "repo-1")
        mgr.add_repo("Backend", "repo-2")
        mgr.add_repo("Backend", "repo-3")
        repos = mgr.list_repos("Backend")
        assert sorted(repos) == ["repo-1", "repo-2", "repo-3"]

    def test_list_repos_empty_topic(self, tmp_path: Path) -> None:
        """Listing repos for a topic with none returns empty list."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Empty")
        assert mgr.list_repos("Empty") == []

    def test_add_duplicate_repo_is_idempotent(self, tmp_path: Path) -> None:
        """Adding the same repo to a topic twice does not duplicate it."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.add_repo("Frontend", "repo-1")
        mgr.add_repo("Frontend", "repo-1")
        repos = mgr.list_repos("Frontend")
        assert repos == ["repo-1"]

    def test_add_repo_to_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        """Adding a repo to a topic that does not exist raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.add_repo("Nonexistent", "repo-1")

    def test_list_repos_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        """Listing repos for a nonexistent topic raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.list_repos("Nonexistent")


class TestRemoveRepo:
    """Tests for removing repos from topics."""

    def test_remove_repo_from_topic(self, tmp_path: Path) -> None:
        """Removing a repo from a topic removes it from list_repos."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.add_repo("Frontend", "repo-1")
        mgr.add_repo("Frontend", "repo-2")
        mgr.remove_repo("Frontend", "repo-1")
        assert mgr.list_repos("Frontend") == ["repo-2"]

    def test_remove_nonexistent_repo_raises(self, tmp_path: Path) -> None:
        """Removing a repo not in the topic raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        with pytest.raises(ValueError, match="Repo not found"):
            mgr.remove_repo("Frontend", "nonexistent-repo")

    def test_remove_repo_from_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        """Removing a repo from a nonexistent topic raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.remove_repo("Nonexistent", "repo-1")


class TestSameRepoMultipleTopics:
    """Tests for a repo appearing in multiple topics."""

    def test_same_repo_in_multiple_topics(self, tmp_path: Path) -> None:
        """The same repo can be added to multiple topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.add_repo("Frontend", "shared-lib")
        mgr.add_repo("Backend", "shared-lib")
        assert "shared-lib" in mgr.list_repos("Frontend")
        assert "shared-lib" in mgr.list_repos("Backend")


class TestListAllRepos:
    """Tests for listing all repos across all topics."""

    def test_list_all_repos(self, tmp_path: Path) -> None:
        """list_all_repos returns unique repos across all topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.add_repo("Frontend", "repo-1")
        mgr.add_repo("Frontend", "repo-2")
        mgr.add_repo("Backend", "repo-2")
        mgr.add_repo("Backend", "repo-3")
        all_repos = mgr.list_all_repos()
        assert sorted(all_repos) == ["repo-1", "repo-2", "repo-3"]

    def test_list_all_repos_empty(self, tmp_path: Path) -> None:
        """list_all_repos with no topics returns empty list."""
        mgr = CodeExplorerTopicManager(tmp_path)
        assert mgr.list_all_repos() == []

    def test_list_all_repos_no_duplicates(self, tmp_path: Path) -> None:
        """list_all_repos does not return duplicates even if repo is in multiple topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("A")
        mgr.create("B")
        mgr.create("C")
        mgr.add_repo("A", "shared")
        mgr.add_repo("B", "shared")
        mgr.add_repo("C", "shared")
        all_repos = mgr.list_all_repos()
        assert all_repos == ["shared"]


class TestUncategorizedRepos:
    """Tests for listing repos not in any topic."""

    def test_list_uncategorized_repos(self, tmp_path: Path) -> None:
        """list_uncategorized_repos returns repos not in any topic."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.add_repo("Frontend", "repo-1")
        all_known = ["repo-1", "repo-2", "repo-3"]
        uncategorized = mgr.list_uncategorized_repos(all_known)
        assert sorted(uncategorized) == ["repo-2", "repo-3"]

    def test_list_uncategorized_repos_all_categorized(self, tmp_path: Path) -> None:
        """When all repos are in topics, uncategorized returns empty list."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("All")
        mgr.add_repo("All", "repo-1")
        mgr.add_repo("All", "repo-2")
        uncategorized = mgr.list_uncategorized_repos(["repo-1", "repo-2"])
        assert uncategorized == []

    def test_list_uncategorized_repos_none_categorized(self, tmp_path: Path) -> None:
        """When no topics exist, all repos are uncategorized."""
        mgr = CodeExplorerTopicManager(tmp_path)
        uncategorized = mgr.list_uncategorized_repos(["repo-1", "repo-2"])
        assert sorted(uncategorized) == ["repo-1", "repo-2"]


class TestDeleteTopic:
    """Tests for deleting topics."""

    def test_delete_topic(self, tmp_path: Path) -> None:
        """Deleting a topic removes it from list_topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("ToDelete")
        mgr.delete("ToDelete")
        assert mgr.list_topics() == []

    def test_delete_topic_removes_references_not_repos(self, tmp_path: Path) -> None:
        """Deleting a topic does not affect repos in other topics."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.add_repo("Frontend", "shared-lib")
        mgr.add_repo("Backend", "shared-lib")
        mgr.delete("Frontend")
        # shared-lib still exists in Backend
        assert "shared-lib" in mgr.list_repos("Backend")

    def test_delete_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        """Deleting a nonexistent topic raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.delete("Nonexistent")

    def test_delete_removes_directory(self, tmp_path: Path) -> None:
        """Deleting a topic removes its directory from disk."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("ToDelete")
        dirs_before = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs_before) == 1
        mgr.delete("ToDelete")
        dirs_after = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs_after) == 0


class TestFindTopicsForRepo:
    """Tests for finding which topics contain a given repo."""

    def test_find_topics_for_repo(self, tmp_path: Path) -> None:
        """find_topics_for_repo returns topics containing the repo."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.create("Empty")
        mgr.add_repo("Frontend", "shared-lib")
        mgr.add_repo("Backend", "shared-lib")
        topics = mgr.find_topics_for_repo("shared-lib")
        assert sorted(topics) == ["Backend", "Frontend"]

    def test_find_topics_for_repo_not_found(self, tmp_path: Path) -> None:
        """find_topics_for_repo returns empty list if repo is not in any topic."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        assert mgr.find_topics_for_repo("unknown-repo") == []


class TestRemoveRepoFromAll:
    """Tests for removing a repo from all topics."""

    def test_remove_repo_from_all(self, tmp_path: Path) -> None:
        """remove_repo_from_all removes the repo from every topic."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        mgr.create("Backend")
        mgr.add_repo("Frontend", "shared-lib")
        mgr.add_repo("Backend", "shared-lib")
        mgr.add_repo("Backend", "other-lib")
        mgr.remove_repo_from_all("shared-lib")
        assert mgr.list_repos("Frontend") == []
        assert mgr.list_repos("Backend") == ["other-lib"]

    def test_remove_repo_from_all_not_in_any(self, tmp_path: Path) -> None:
        """remove_repo_from_all does not raise if repo is not in any topic."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Frontend")
        # Should not raise
        mgr.remove_repo_from_all("nonexistent-repo")


class TestRenameTopic:
    """Tests for renaming topics."""

    def test_rename_topic(self, tmp_path: Path) -> None:
        """Renaming a topic updates its display name in topic.json."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Old Name")
        mgr.add_repo("Old Name", "repo-1")
        mgr.rename("Old Name", "New Name")
        topics = mgr.list_topics()
        assert "New Name" in topics
        assert "Old Name" not in topics
        # Repos are preserved
        assert mgr.list_repos("New Name") == ["repo-1"]

    def test_rename_nonexistent_topic_raises(self, tmp_path: Path) -> None:
        """Renaming a nonexistent topic raises ValueError."""
        mgr = CodeExplorerTopicManager(tmp_path)
        with pytest.raises(ValueError, match="Topic not found"):
            mgr.rename("Nonexistent", "New")

    def test_rename_preserves_directory(self, tmp_path: Path) -> None:
        """Renaming a topic does not rename the directory (only updates metadata)."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Original")
        dirs_before = {d.name for d in tmp_path.iterdir() if d.is_dir()}
        mgr.rename("Original", "Renamed")
        dirs_after = {d.name for d in tmp_path.iterdir() if d.is_dir()}
        assert dirs_before == dirs_after

    def test_rename_to_existing_display_name_raises(self, tmp_path: Path) -> None:
        """Renaming a topic to a name already used by another topic raises."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.create("Beta")
        with pytest.raises(ValueError, match="already exists"):
            mgr.rename("Alpha", "Beta")

    def test_rename_to_same_name_is_noop(self, tmp_path: Path) -> None:
        """Renaming a topic to its own current name does not raise."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Alpha")
        mgr.rename("Alpha", "Alpha")
        assert mgr.list_topics() == ["Alpha"]

    @pytest.mark.parametrize("new_name", ["foo/bar", "a\\b"])
    def test_rename_rejects_path_separators(
        self, tmp_path: Path, new_name: str
    ) -> None:
        """Renaming to a name with path separators is rejected."""
        mgr = CodeExplorerTopicManager(tmp_path)
        mgr.create("Safe")
        with pytest.raises(ValueError, match="path separator"):
            mgr.rename("Safe", new_name)


class TestListTopicsNoDuplicates:
    """list_topics must never return duplicate display names."""

    def test_no_duplicate_display_names(self, tmp_path: Path) -> None:
        """Even if two directories have the same display name, list_topics deduplicates."""
        mgr = CodeExplorerTopicManager(tmp_path)
        # Simulate the bug: create two dirs with same display name
        import json

        (tmp_path / "dir-a").mkdir()
        (tmp_path / "dir-a" / "topic.json").write_text(
            json.dumps({"name": "RLMs", "repos": ["repo-1"]})
        )
        (tmp_path / "dir-b").mkdir()
        (tmp_path / "dir-b" / "topic.json").write_text(
            json.dumps({"name": "RLMs", "repos": ["repo-2"]})
        )
        topics = mgr.list_topics()
        assert topics == ["RLMs"]
