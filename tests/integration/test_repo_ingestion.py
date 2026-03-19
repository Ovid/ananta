"""Integration tests for repository ingestion."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from shesha import Shesha
from shesha.exceptions import RepoIngestError
from shesha.repo.ingester import RepoIngester


@pytest.fixture
def sample_git_repo(tmp_path: Path) -> Path:
    """Create a sample git repository for testing."""
    repo_path = tmp_path / "sample-repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        capture_output=True,
    )

    # Create some files
    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text(
        "def main():\n    print('Hello')\n\nif __name__ == '__main__':\n    main()\n"
    )
    (repo_path / "README.md").write_text("# Sample Repo\n\nA test repository.\n")

    # Commit
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
    )

    return repo_path


class TestLocalPathRestriction:
    """Tests for allow_local_paths flag on RepoIngester."""

    def test_rejects_local_path_when_disabled(self, sample_git_repo: Path, tmp_path: Path):
        """ingest() raises when allow_local_paths=False and URL is a local path."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path / "storage")
        from shesha.parser import create_default_registry

        registry = create_default_registry()
        ingester = RepoIngester(storage_path=tmp_path, allow_local_paths=False)

        with pytest.raises(RepoIngestError, match="Local path ingestion is disabled"):
            ingester.ingest(
                storage=storage,
                parser_registry=registry,
                url=str(sample_git_repo),
                name="blocked-project",
                path=None,
                is_update=False,
            )

    def test_allows_local_path_by_default(self, sample_git_repo: Path, tmp_path: Path):
        """ingest() works for local paths with default settings."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path / "storage")
        from shesha.parser import create_default_registry

        registry = create_default_registry()
        ingester = RepoIngester(storage_path=tmp_path)

        result = ingester.ingest(
            storage=storage,
            parser_registry=registry,
            url=str(sample_git_repo),
            name="allowed-project",
            path=None,
            is_update=False,
        )
        assert result.files_ingested >= 1


class TestRepoIngestion:
    """Integration tests for create_project_from_repo."""

    def test_ingest_local_repo(self, sample_git_repo: Path, tmp_path: Path):
        """Can ingest a local git repository."""
        storage_path = tmp_path / "shesha-storage"

        with patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=storage_path)

            result = shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            assert result.status == "created"
            assert result.files_ingested >= 2  # At least main.py and README.md
            assert result.project.project_id == "sample-project"

    def test_ingest_with_line_numbers(self, sample_git_repo: Path, tmp_path: Path):
        """Ingested files have line numbers."""
        storage_path = tmp_path / "shesha-storage"

        with patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=storage_path)

            shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            docs = shesha.storage.load_all_documents("sample-project")
            main_doc = next(d for d in docs if "main.py" in d.name)

            assert "=== FILE:" in main_doc.content
            assert "1|" in main_doc.content

    def test_unchanged_on_second_call(self, sample_git_repo: Path, tmp_path: Path):
        """Second call returns unchanged when no changes."""
        storage_path = tmp_path / "shesha-storage"

        with patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=storage_path)

            # First call
            shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            # Second call
            result = shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            assert result.status == "unchanged"

    def test_updates_available_after_change(self, sample_git_repo: Path, tmp_path: Path):
        """Returns updates_available after repo changes."""
        storage_path = tmp_path / "shesha-storage"

        with patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=storage_path)

            # First call
            shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            # Modify repo
            (sample_git_repo / "src" / "new_file.py").write_text("# New file\n")
            subprocess.run(["git", "add", "."], cwd=sample_git_repo, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Add new file"],
                cwd=sample_git_repo,
                capture_output=True,
            )

            # Second call
            result = shesha.create_project_from_repo(
                url=str(sample_git_repo),
                name="sample-project",
            )

            assert result.status == "updates_available"
