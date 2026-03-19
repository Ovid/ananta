"""Tests for RepoIngester."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.exceptions import AuthenticationError, RepoIngestError
from shesha.repo.ingester import RepoIngester
from shesha.security.paths import PathTraversalError


@pytest.fixture
def ingester(tmp_path: Path) -> RepoIngester:
    return RepoIngester(storage_path=tmp_path)


class TestRepoIngester:
    """Tests for RepoIngester class."""

    def test_init_creates_repos_dir(self, ingester: RepoIngester, tmp_path: Path):
        """RepoIngester creates repos directory on init."""
        assert (tmp_path / "repos").is_dir()

    def test_is_local_path_absolute(self, ingester: RepoIngester):
        """is_local_path returns True for absolute paths."""
        assert ingester.is_local_path("/home/user/repo")

    def test_is_local_path_home(self, ingester: RepoIngester):
        """is_local_path returns True for home-relative paths."""
        assert ingester.is_local_path("~/projects/repo")

    def test_is_local_path_relative_dot(self, ingester: RepoIngester):
        """is_local_path returns True for ./ relative paths."""
        assert ingester.is_local_path("./some/repo")

    def test_is_local_path_relative_dotdot(self, ingester: RepoIngester):
        """is_local_path returns True for ../ relative paths."""
        assert ingester.is_local_path("../sibling/repo")

    def test_is_local_path_rejects_bare_name(
        self, ingester: RepoIngester, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """is_local_path returns False for bare names even if they exist on disk."""
        target = tmp_path / "somerepo"
        target.mkdir()
        monkeypatch.chdir(tmp_path)
        assert not ingester.is_local_path("somerepo")

    def test_is_local_path_url(self, ingester: RepoIngester):
        """is_local_path returns False for URLs."""
        assert not ingester.is_local_path("https://github.com/org/repo")
        assert not ingester.is_local_path("git@github.com:org/repo.git")

    def test_detect_host_github(self, ingester: RepoIngester):
        """detect_host identifies GitHub URLs."""
        assert ingester.detect_host("https://github.com/org/repo") == "github.com"
        assert ingester.detect_host("git@github.com:org/repo.git") == "github.com"

    def test_detect_host_gitlab(self, ingester: RepoIngester):
        """detect_host identifies GitLab URLs."""
        assert ingester.detect_host("https://gitlab.com/org/repo") == "gitlab.com"

    def test_detect_host_bitbucket(self, ingester: RepoIngester):
        """detect_host identifies Bitbucket URLs."""
        assert ingester.detect_host("https://bitbucket.org/org/repo") == "bitbucket.org"

    def test_detect_host_local(self, ingester: RepoIngester):
        """detect_host returns None for local paths."""
        assert ingester.detect_host("/home/user/repo") is None

    def test_is_git_repo_returns_true_for_git_dir(self, ingester: RepoIngester, tmp_path: Path):
        """is_git_repo returns True for directories with .git."""
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        assert ingester.is_git_repo(repo_dir) is True

    def test_is_git_repo_returns_false_for_non_git_dir(
        self, ingester: RepoIngester, tmp_path: Path
    ):
        """is_git_repo returns False for directories without .git."""
        non_repo_dir = tmp_path / "not-a-repo"
        non_repo_dir.mkdir()
        assert ingester.is_git_repo(non_repo_dir) is False

    def test_is_git_repo_returns_false_for_nonexistent(
        self, ingester: RepoIngester, tmp_path: Path
    ):
        """is_git_repo returns False for paths that don't exist."""
        assert ingester.is_git_repo(tmp_path / "nonexistent") is False


class TestTokenResolution:
    """Tests for token resolution logic."""

    def test_explicit_token_takes_precedence(self, ingester: RepoIngester):
        """Explicit token parameter wins over env vars."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token="explicit_token",
            )
            assert token == "explicit_token"

    def test_github_env_token(self, ingester: RepoIngester):
        """GITHUB_TOKEN env var used for github.com."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "gh_token"}, clear=True):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token=None,
            )
            assert token == "gh_token"

    def test_gitlab_env_token(self, ingester: RepoIngester):
        """GITLAB_TOKEN env var used for gitlab.com."""
        with patch.dict(os.environ, {"GITLAB_TOKEN": "gl_token"}, clear=True):
            token = ingester.resolve_token(
                url="https://gitlab.com/org/repo",
                explicit_token=None,
            )
            assert token == "gl_token"

    def test_no_token_returns_none(self, ingester: RepoIngester):
        """Returns None when no token available."""
        with patch.dict(os.environ, {}, clear=True):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token=None,
            )
            assert token is None


class TestGitClone:
    """Tests for git clone functionality."""

    def test_clone_creates_project_dir(self, ingester: RepoIngester, tmp_path: Path):
        """clone() creates directory for the project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
            )

            assert (tmp_path / "repos" / "my-project").is_dir()

    def test_clone_uses_depth_1(self, ingester: RepoIngester):
        """clone() uses shallow clone (depth=1)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
            )

            call_args = mock_run.call_args[0][0]
            assert "--depth=1" in call_args

    def test_clone_uses_askpass_for_token(self, ingester: RepoIngester):
        """clone() passes token via GIT_ASKPASS, not in command-line args."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
                token="my_token",
            )

            call_args = mock_run.call_args[0][0]
            call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
            # Token must NOT appear in command-line args
            cmd_str = " ".join(call_args)
            assert "my_token" not in cmd_str
            # Token must NOT appear in URL
            url_in_cmd = [a for a in call_args if "github.com" in a][0]
            assert "my_token" not in url_in_cmd
            # GIT_ASKPASS must be set in env
            env = call_kwargs.get("env", {})
            assert "GIT_ASKPASS" in env

    def test_clone_askpass_passes_token_via_env(self, ingester: RepoIngester):
        """clone() passes token via GIT_TOKEN env var, not in args."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
                token="my_token",
            )

            call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
            env = call_kwargs.get("env", {})
            assert env["GIT_TOKEN"] == "my_token"
            assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_clone_without_token_has_no_askpass(self, ingester: RepoIngester):
        """clone() does not set GIT_ASKPASS when no token."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
            )

            call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
            env = call_kwargs.get("env")
            if env:
                assert "GIT_ASKPASS" not in env

    def test_inject_token_method_removed(self, ingester: RepoIngester):
        """_inject_token private method no longer exists."""
        assert not hasattr(ingester, "_inject_token")

    def test_clone_auth_failure_raises(self, ingester: RepoIngester):
        """clone() raises AuthenticationError on auth failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: Authentication failed",
            )

            with pytest.raises(AuthenticationError):
                ingester.clone(
                    url="https://github.com/org/private-repo",
                    project_id="my-project",
                )

    def test_clone_other_failure_raises(self, ingester: RepoIngester):
        """clone() raises RepoIngestError on other failures."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: repository not found",
            )

            with pytest.raises(RepoIngestError):
                ingester.clone(
                    url="https://github.com/org/nonexistent",
                    project_id="my-project",
                )


class TestSHATracking:
    """Tests for SHA tracking functionality."""

    def test_save_sha_creates_file(self, ingester: RepoIngester, tmp_path: Path):
        """save_sha() creates metadata file with SHA."""
        ingester.save_sha("my-project", "abc123def456")

        meta_path = tmp_path / "repos" / "my-project" / "_repo_meta.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["head_sha"] == "abc123def456"

    def test_save_sha_preserves_existing_metadata(
        self, ingester: RepoIngester, tmp_path: Path
    ):
        """save_sha() preserves existing keys like source_url."""
        ingester.save_source_url("my-project", "https://example.com/repo")
        ingester.save_sha("my-project", "abc123def456")

        meta_path = tmp_path / "repos" / "my-project" / "_repo_meta.json"
        data = json.loads(meta_path.read_text())
        assert data["head_sha"] == "abc123def456"
        assert data["source_url"] == "https://example.com/repo"

    def test_get_saved_sha(self, ingester: RepoIngester, tmp_path: Path):
        """get_saved_sha() returns stored SHA."""
        (tmp_path / "repos" / "my-project").mkdir(parents=True)
        meta_path = tmp_path / "repos" / "my-project" / "_repo_meta.json"
        meta_path.write_text(json.dumps({"head_sha": "abc123"}))

        sha = ingester.get_saved_sha("my-project")
        assert sha == "abc123"

    def test_get_saved_sha_missing_returns_none(self, ingester: RepoIngester):
        """get_saved_sha() returns None if no metadata."""
        sha = ingester.get_saved_sha("nonexistent-project")
        assert sha is None

    def test_get_repo_url(self, ingester: RepoIngester, tmp_path: Path):
        """get_repo_url() returns git remote origin URL."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/org/repo\n",
            )

            url = ingester.get_repo_url("my-project")
            assert url == "https://github.com/org/repo"
            assert "remote" in mock_run.call_args[0][0]
            assert "get-url" in mock_run.call_args[0][0]

    def test_get_repo_url_returns_none_when_no_repo(self, ingester: RepoIngester):
        """get_repo_url() returns None when repo directory doesn't exist."""
        url = ingester.get_repo_url("nonexistent-project")
        assert url is None

    def test_get_repo_url_returns_none_when_no_remote(self, ingester: RepoIngester, tmp_path: Path):
        """get_repo_url() returns None when git remote fails."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: No such remote 'origin'",
            )

            url = ingester.get_repo_url("my-project")
            assert url is None

    def test_get_remote_sha(self, ingester: RepoIngester):
        """get_remote_sha() calls git ls-remote."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123def456789\tHEAD\n",
            )

            sha = ingester.get_remote_sha("https://github.com/org/repo")
            assert sha == "abc123def456789"
            assert "ls-remote" in mock_run.call_args[0][0]

    def test_get_local_sha(self, ingester: RepoIngester, tmp_path: Path):
        """get_local_sha() returns HEAD SHA from local repo."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123def456789\n",
            )

            sha = ingester.get_local_sha("my-project")
            assert sha == "abc123def456789"


class TestFileListing:
    """Tests for file listing functionality."""

    def test_list_files_uses_git_ls_files(self, ingester: RepoIngester, tmp_path: Path):
        """list_files() uses git ls-files."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/main.py\nREADME.md\ntests/test_main.py\n",
            )

            files = ingester.list_files("my-project")
            assert files == ["src/main.py", "README.md", "tests/test_main.py"]

    def test_list_files_with_subdirectory(self, ingester: RepoIngester, tmp_path: Path):
        """list_files() filters to subdirectory when specified."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/main.py\nsrc/utils.py\n",
            )

            ingester.list_files("my-project", subdir="src/")

            call_args = mock_run.call_args[0][0]
            assert "src/" in call_args

    def test_list_files_empty_repo(self, ingester: RepoIngester, tmp_path: Path):
        """list_files() returns empty list for empty repo."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")

            files = ingester.list_files("my-project")
            assert files == []


class TestSourceURLTracking:
    """Tests for source URL tracking functionality."""

    def test_save_source_url_stores_url(self, tmp_path: Path):
        """save_source_url stores the original source URL in metadata."""
        ingester = RepoIngester(tmp_path)

        ingester.save_source_url("my-project", "https://github.com/org/repo")

        assert ingester.get_source_url("my-project") == "https://github.com/org/repo"

    def test_save_source_url_stores_local_path(self, tmp_path: Path):
        """save_source_url stores local paths correctly."""
        ingester = RepoIngester(tmp_path)

        ingester.save_source_url("local-project", "/path/to/local/repo")

        assert ingester.get_source_url("local-project") == "/path/to/local/repo"

    def test_get_source_url_returns_none_when_not_set(self, tmp_path: Path):
        """get_source_url returns None when no URL has been saved."""
        ingester = RepoIngester(tmp_path)

        assert ingester.get_source_url("nonexistent") is None


class TestDeleteRepo:
    """Tests for delete_repo functionality."""

    def test_delete_repo_removes_cloned_directory(self, tmp_path: Path):
        """delete_repo removes the cloned repository directory."""
        ingester = RepoIngester(tmp_path)
        repo_path = ingester.repos_dir / "my-project"
        repo_path.mkdir(parents=True)
        (repo_path / "file.txt").write_text("content")

        ingester.delete_repo("my-project")

        assert not repo_path.exists()

    def test_delete_repo_does_nothing_for_nonexistent(self, tmp_path: Path):
        """delete_repo silently succeeds for non-existent repos."""
        ingester = RepoIngester(tmp_path)

        # Should not raise
        ingester.delete_repo("nonexistent")


class TestGitFetchPull:
    """Tests for git fetch and pull functionality."""

    def test_fetch_calls_git_fetch(self, ingester: RepoIngester, tmp_path: Path):
        """fetch() calls git fetch."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            ingester.fetch("my-project")

            call_args = mock_run.call_args[0][0]
            assert "fetch" in call_args

    def test_pull_calls_git_pull(self, ingester: RepoIngester, tmp_path: Path):
        """pull() calls git pull."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            ingester.pull("my-project")

            call_args = mock_run.call_args[0][0]
            assert "pull" in call_args

    def test_fetch_failure_raises(self, ingester: RepoIngester, tmp_path: Path):
        """fetch() raises RepoIngestError on non-zero return code."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: could not read from remote",
            )

            with pytest.raises(RepoIngestError):
                ingester.fetch("my-project")

    def test_pull_failure_raises(self, ingester: RepoIngester, tmp_path: Path):
        """pull() raises RepoIngestError on failure."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="merge conflict",
            )

            with pytest.raises(RepoIngestError):
                ingester.pull("my-project")


class TestSubprocessTimeouts:
    """Tests for subprocess timeout enforcement."""

    def test_clone_has_timeout(self, ingester: RepoIngester):
        """clone() passes timeout to subprocess.run."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone("https://github.com/org/repo", "my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] > 0

    def test_pull_has_timeout(self, ingester: RepoIngester, tmp_path: Path):
        """pull() passes timeout to subprocess.run."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            ingester.pull("my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_get_remote_sha_has_timeout(self, ingester: RepoIngester):
        """get_remote_sha() passes timeout to subprocess.run."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123\tHEAD\n",
            )

            ingester.get_remote_sha("https://github.com/org/repo")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_fetch_has_timeout(self, ingester: RepoIngester, tmp_path: Path):
        """fetch() passes timeout to subprocess.run."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            ingester.fetch("my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_get_local_sha_has_timeout(self, ingester: RepoIngester, tmp_path: Path):
        """get_sha_from_path() passes timeout to subprocess.run."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")

            ingester.get_local_sha("my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_list_files_has_timeout(self, ingester: RepoIngester, tmp_path: Path):
        """list_files_from_path() passes timeout to subprocess.run."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="file.py\n")

            ingester.list_files("my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_get_repo_url_has_timeout(self, ingester: RepoIngester, tmp_path: Path):
        """get_repo_url() passes timeout to subprocess.run."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="url\n")

            ingester.get_repo_url("my-project")

            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs

    def test_clone_timeout_raises_repo_ingest_error(self, ingester: RepoIngester):
        """clone() converts TimeoutExpired to RepoIngestError."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=300)

            with pytest.raises(RepoIngestError):
                ingester.clone("https://github.com/org/repo", "my-project")

    def test_pull_timeout_raises_repo_ingest_error(self, ingester: RepoIngester, tmp_path: Path):
        """pull() converts TimeoutExpired to RepoIngestError."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=120)

            with pytest.raises(RepoIngestError):
                ingester.pull("my-project")

    def test_fetch_timeout_raises_repo_ingest_error(self, ingester: RepoIngester, tmp_path: Path):
        """fetch() converts TimeoutExpired to RepoIngestError."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=120)

            with pytest.raises(RepoIngestError):
                ingester.fetch("my-project")

    def test_list_files_timeout_raises_repo_ingest_error(self, ingester: RepoIngester):
        """list_files_from_path() raises RepoIngestError on timeout instead of returning []."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

            with pytest.raises(RepoIngestError):
                ingester.list_files_from_path(Path("/fake/repo"))

    def test_get_remote_sha_timeout_returns_none(self, ingester: RepoIngester):
        """get_remote_sha() returns None on timeout."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

            result = ingester.get_remote_sha("https://github.com/org/repo")

            assert result is None


class TestTokenInGetRemoteSha:
    """Tests for token handling in get_remote_sha."""

    def test_get_remote_sha_uses_token_when_provided(self, ingester: RepoIngester):
        """get_remote_sha uses askpass when token is provided."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123\tHEAD\n",
            )

            ingester.get_remote_sha("https://github.com/org/repo", token="my_token")

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env", {})
            assert "GIT_ASKPASS" in env
            assert env["GIT_TOKEN"] == "my_token"
            assert env["GIT_TERMINAL_PROMPT"] == "0"


class TestNoPromptEnv:
    """Tests for GIT_TERMINAL_PROMPT=0 in non-token paths."""

    def test_clone_without_token_sets_no_prompt(self, ingester: RepoIngester):
        """clone() sets GIT_TERMINAL_PROMPT=0 even without a token."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone("https://github.com/org/repo", "my-project")

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env", {})
            assert env.get("GIT_TERMINAL_PROMPT") == "0"

    def test_get_remote_sha_without_token_sets_no_prompt(self, ingester: RepoIngester):
        """get_remote_sha() sets GIT_TERMINAL_PROMPT=0 even without a token."""
        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\tHEAD\n")

            ingester.get_remote_sha("https://github.com/org/repo")

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env", {})
            assert env.get("GIT_TERMINAL_PROMPT") == "0"

    def test_fetch_sets_no_prompt(self, ingester: RepoIngester, tmp_path: Path):
        """fetch() sets GIT_TERMINAL_PROMPT=0 to prevent interactive prompts."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            ingester.fetch("my-project")

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env", {})
            assert env.get("GIT_TERMINAL_PROMPT") == "0"

    def test_pull_sets_no_prompt(self, ingester: RepoIngester, tmp_path: Path):
        """pull() sets GIT_TERMINAL_PROMPT=0 to prevent interactive prompts."""
        repo_path = tmp_path / "repos" / "my-project"
        repo_path.mkdir(parents=True)

        with patch("shesha.repo.ingester.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.pull("my-project")

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env", {})
            assert env.get("GIT_TERMINAL_PROMPT") == "0"


class TestPathTraversalProtection:
    """Tests for path traversal protection in RepoIngester."""

    def test_repo_path_helper_exists(self, ingester: RepoIngester):
        """_repo_path helper method exists and returns safe path."""
        path = ingester._repo_path("valid-project")
        assert path == ingester.repos_dir / "valid-project"

    def test_repo_path_blocks_traversal(self, ingester: RepoIngester):
        """_repo_path raises PathTraversalError on traversal attempt."""
        with pytest.raises(PathTraversalError):
            ingester._repo_path("../escape")

    def test_repo_path_blocks_absolute_path(self, ingester: RepoIngester):
        """_repo_path raises PathTraversalError on absolute path."""
        with pytest.raises(PathTraversalError):
            ingester._repo_path("/etc/passwd")

    def test_clone_blocks_traversal(self, ingester: RepoIngester):
        """clone() raises PathTraversalError on traversal attempt."""
        with pytest.raises(PathTraversalError):
            ingester.clone("https://github.com/org/repo", "../escape")

    def test_save_sha_blocks_traversal(self, ingester: RepoIngester):
        """save_sha() raises PathTraversalError on traversal attempt."""
        with pytest.raises(PathTraversalError):
            ingester.save_sha("../escape", "abc123")

    def test_delete_repo_blocks_traversal(self, ingester: RepoIngester):
        """delete_repo() raises PathTraversalError on traversal attempt."""
        with pytest.raises(PathTraversalError):
            ingester.delete_repo("../escape")
