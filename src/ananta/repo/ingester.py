"""Git repository ingester."""

import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ananta.exceptions import AuthenticationError, NoParserError, ParseError, RepoIngestError
from ananta.models import ParsedDocument
from ananta.security.paths import safe_path

if TYPE_CHECKING:
    from ananta.parser.registry import ParserRegistry
    from ananta.storage.base import StorageBackend


@dataclass
class IngestResult:
    """Result of ingesting files from a repository into storage."""

    files_ingested: int
    files_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


# Timeouts for git subprocess calls (seconds)
GIT_CLONE_TIMEOUT = 300
GIT_PULL_TIMEOUT = 120
GIT_FETCH_TIMEOUT = 120
GIT_LS_REMOTE_TIMEOUT = 30
GIT_LOCAL_TIMEOUT = 30


logger = logging.getLogger(__name__)


class RepoIngester:
    """Handles git repository cloning, updating, and file extraction."""

    # Host to environment variable mapping
    HOST_TO_ENV_VAR = {
        "github.com": "GITHUB_TOKEN",
        "gitlab.com": "GITLAB_TOKEN",
        "bitbucket.org": "BITBUCKET_TOKEN",
    }

    def __init__(
        self,
        storage_path: Path | str,
        allow_local_paths: bool = True,
    ) -> None:
        """Initialize with storage path for cloned repos.

        Args:
            storage_path: Path to store cloned repos and metadata.
            allow_local_paths: Whether to allow ingesting from local paths.
                Defaults to True for CLI/library use. Web explorers should
                set this to False to prevent unauthorized filesystem reads.
        """
        self.storage_path = Path(storage_path)
        self.repos_dir = self.storage_path / "repos"
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self._meta_lock = threading.Lock()
        self._allow_local_paths = allow_local_paths

    def _repo_path(self, project_id: str) -> Path:
        """Get safe path for a project's repo directory."""
        return safe_path(self.repos_dir, project_id)

    # Only allow safe git transport protocols — blocks ext:: (RCE) and
    # file:// (bypasses is_local_path() check, enabling local filesystem reads).
    _GIT_SAFE_PROTOCOLS = "https:ssh"

    @staticmethod
    def _no_prompt_env() -> dict[str, str]:
        """Return env dict with GIT_TERMINAL_PROMPT=0 to prevent interactive prompts."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ALLOW_PROTOCOL"] = RepoIngester._GIT_SAFE_PROTOCOLS
        return env

    def is_local_path(self, url: str) -> bool:
        """Check if url is a local filesystem path."""
        return (
            url.startswith("/")
            or url.startswith("~")
            or url.startswith("./")
            or url.startswith("../")
        )

    def is_git_repo(self, path: Path) -> bool:
        """Check if path is a git repository.

        Args:
            path: Filesystem path to check.

        Returns:
            True if path exists and contains a .git directory.
        """
        return path.exists() and (path / ".git").exists()

    def detect_host(self, url: str) -> str | None:
        """Detect the git host from a URL."""
        if self.is_local_path(url):
            return None

        # Handle SSH URLs (git@github.com:org/repo.git)
        ssh_match = re.match(r"git@([^:]+):", url)
        if ssh_match:
            return ssh_match.group(1)

        # Handle HTTPS URLs
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc

        return None

    def resolve_token(self, url: str, explicit_token: str | None) -> str | None:
        """Resolve authentication token for a URL.

        Priority: explicit token > env var > None (system git auth)
        """
        if explicit_token:
            return explicit_token

        host = self.detect_host(url)
        if host and host in self.HOST_TO_ENV_VAR:
            env_var = self.HOST_TO_ENV_VAR[host]
            return os.environ.get(env_var)

        return None

    def clone(
        self,
        url: str,
        project_id: str,
        token: str | None = None,
    ) -> Path:
        """Clone a git repository."""
        repo_path = self._repo_path(project_id)
        repo_path.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone", "--depth=1", url, str(repo_path)]

        if token:
            env, askpass_path = self._create_askpass(token)
        else:
            env = self._no_prompt_env()
            askpass_path = None

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env, timeout=GIT_CLONE_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise RepoIngestError(
                url, RuntimeError(f"Git clone timed out after {GIT_CLONE_TIMEOUT}s")
            )
        finally:
            if askpass_path is not None:
                askpass_path.unlink(missing_ok=True)

        if result.returncode != 0:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            if "Authentication failed" in result.stderr:
                raise AuthenticationError(url)
            raise RepoIngestError(url, RuntimeError(result.stderr))

        return repo_path

    @staticmethod
    def _create_askpass(token: str) -> tuple[dict[str, str], Path]:
        """Create a GIT_ASKPASS script that supplies the token via stdout.

        Returns env dict and path to the temp script (caller must clean up).
        """
        fd, path = tempfile.mkstemp(suffix="_git_askpass.sh")
        try:
            with os.fdopen(fd, "w") as f:
                f.write('#!/bin/sh\necho "$GIT_TOKEN"\n')
            os.chmod(path, stat.S_IRWXU)
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise

        env = os.environ.copy()
        env["GIT_ASKPASS"] = path
        env["GIT_TOKEN"] = token
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ALLOW_PROTOCOL"] = RepoIngester._GIT_SAFE_PROTOCOLS
        return env, Path(path)

    def _load_meta(self, meta_path: Path) -> dict[str, str]:
        """Load repo metadata JSON, returning {} on missing or corrupt file."""
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {}  # Corrupt file — start fresh

    def _save_meta_field(self, project_id: str, key: str, value: str) -> None:
        """Save a single field to _repo_meta.json under a lock."""
        repo_path = self._repo_path(project_id)
        repo_path.mkdir(parents=True, exist_ok=True)
        meta_path = repo_path / "_repo_meta.json"

        with self._meta_lock:
            data = self._load_meta(meta_path)
            data[key] = value
            meta_path.write_text(json.dumps(data))

    def save_sha(self, project_id: str, sha: str) -> None:
        """Save the HEAD SHA for a project."""
        self._save_meta_field(project_id, "head_sha", sha)

    def save_source_url(self, project_id: str, url: str) -> None:
        """Save the source URL for a project."""
        self._save_meta_field(project_id, "source_url", url)

    def get_source_url(self, project_id: str) -> str | None:
        """Get the saved source URL for a project."""
        meta_path = self._repo_path(project_id) / "_repo_meta.json"
        with self._meta_lock:
            data = self._load_meta(meta_path)
        url = data.get("source_url")
        return str(url) if url is not None else None

    def get_saved_sha(self, project_id: str) -> str | None:
        """Get the saved HEAD SHA for a project."""
        meta_path = self._repo_path(project_id) / "_repo_meta.json"
        with self._meta_lock:
            data = self._load_meta(meta_path)
        sha = data.get("head_sha")
        return str(sha) if sha is not None else None

    def save_path(self, project_id: str, path: str) -> None:
        """Save the subdirectory scope for a project."""
        self._save_meta_field(project_id, "path", path)

    def get_saved_path(self, project_id: str) -> str | None:
        """Get the saved subdirectory scope for a project."""
        meta_path = self._repo_path(project_id) / "_repo_meta.json"
        with self._meta_lock:
            data = self._load_meta(meta_path)
        p = data.get("path")
        return str(p) if p is not None else None

    def get_remote_sha(self, url: str, token: str | None = None) -> str | None:
        """Get the HEAD SHA from remote repository."""
        cmd = ["git", "ls-remote", url, "HEAD"]

        if token:
            env, askpass_path = self._create_askpass(token)
        else:
            env = self._no_prompt_env()
            askpass_path = None

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env, timeout=GIT_LS_REMOTE_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            return None
        finally:
            if askpass_path is not None:
                askpass_path.unlink(missing_ok=True)

        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split()
        return parts[0] if parts else None

    def get_repo_url(self, project_id: str) -> str | None:
        """Get the remote origin URL for a cloned repo.

        Args:
            project_id: ID of the cloned repo.

        Returns:
            The remote origin URL, or None if not found.
        """
        repo_path = self._repo_path(project_id)
        if not repo_path.exists():
            return None

        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_LOCAL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return None

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def get_local_sha(self, project_id: str) -> str | None:
        """Get the HEAD SHA from a local cloned repo."""
        repo_path = self._repo_path(project_id)
        return self.get_sha_from_path(repo_path)

    def get_sha_from_path(self, repo_path: Path) -> str | None:
        """Get the HEAD SHA from a repository at the given path."""
        if not repo_path.exists():
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_LOCAL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return None

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def list_files(self, project_id: str, subdir: str | None = None) -> list[str]:
        """List tracked files in a cloned repository.

        Args:
            project_id: ID of the cloned repo.
            subdir: Optional subdirectory to filter to.

        Returns:
            List of relative file paths.
        """
        repo_path = self._repo_path(project_id)
        return self.list_files_from_path(repo_path, subdir)

    def list_files_from_path(self, repo_path: Path, subdir: str | None = None) -> list[str]:
        """List tracked files in a repository at the given path.

        Args:
            repo_path: Path to the git repository.
            subdir: Optional subdirectory to filter to.

        Returns:
            List of relative file paths.
        """
        cmd = ["git", "ls-files"]
        if subdir:
            cmd.append(subdir)

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_LOCAL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RepoIngestError(
                str(repo_path),
                RuntimeError(f"git ls-files timed out after {GIT_LOCAL_TIMEOUT}s"),
            )

        if result.returncode != 0:
            return []

        files = result.stdout.strip().split("\n")
        return [f for f in files if f]

    def fetch(self, project_id: str) -> None:
        """Fetch updates from remote.

        Raises:
            RepoIngestError: If fetch fails or times out.
        """
        repo_path = self._repo_path(project_id)
        url = f"repo at {repo_path}"

        try:
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_FETCH_TIMEOUT,
                env=self._no_prompt_env(),
            )
        except subprocess.TimeoutExpired:
            raise RepoIngestError(
                url, RuntimeError(f"Git fetch timed out after {GIT_FETCH_TIMEOUT}s")
            )

        if result.returncode != 0:
            raise RepoIngestError(url, RuntimeError(result.stderr))

    def pull(self, project_id: str) -> None:
        """Pull updates from remote.

        Raises:
            RepoIngestError: If pull fails.
        """
        repo_path = self._repo_path(project_id)
        url = f"repo at {repo_path}"

        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_PULL_TIMEOUT,
                env=self._no_prompt_env(),
            )
        except subprocess.TimeoutExpired:
            raise RepoIngestError(
                url, RuntimeError(f"Git pull timed out after {GIT_PULL_TIMEOUT}s")
            )

        if result.returncode != 0:
            raise RepoIngestError(url, RuntimeError(result.stderr))

    def delete_repo(self, project_id: str) -> None:
        """Delete the cloned repository directory for a project."""
        repo_path = self._repo_path(project_id)
        if repo_path.exists():
            shutil.rmtree(repo_path)

    def ingest(
        self,
        storage: "StorageBackend",
        parser_registry: "ParserRegistry",
        url: str,
        name: str,
        path: str | None,
        *,
        is_update: bool,
    ) -> IngestResult:
        """Ingest files from repository into project storage.

        For new projects (is_update=False): creates project, ingests files,
        and deletes the project if ingestion fails.

        For updates (is_update=True): ingests into a staging project, then
        swaps docs into the target project. If ingestion fails, the staging
        project is cleaned up and the original is untouched.
        """
        staging_name = f"_staging_{name}_{uuid.uuid4().hex[:8]}" if is_update else name
        is_local = self.is_local_path(url)
        if is_local and not self._allow_local_paths:
            raise RepoIngestError(url, RuntimeError("Local path ingestion is disabled"))

        try:
            if not is_update:
                storage.create_project(name)
            else:
                storage.create_project(staging_name)

            if is_local:
                repo_path = Path(url).expanduser()
            else:
                repo_path = self._repo_path(name)

            files = self.list_files_from_path(repo_path, subdir=path)
            files_ingested = 0
            files_skipped = 0
            warnings: list[str] = []

            for file_path in files:
                full_path = repo_path / file_path
                try:
                    parser = parser_registry.find_parser(full_path)
                    if parser is None:
                        files_skipped += 1
                        continue

                    doc = parser.parse(full_path, include_line_numbers=True, file_path=file_path)
                    doc = ParsedDocument(
                        name=file_path,
                        content=doc.content,
                        format=doc.format,
                        metadata=doc.metadata,
                        char_count=doc.char_count,
                        parse_warnings=doc.parse_warnings,
                    )
                    storage.store_document(staging_name, doc)
                    files_ingested += 1
                except (ParseError, NoParserError) as e:
                    files_skipped += 1
                    warnings.append(f"Failed to parse {file_path}: {e}")
                except Exception as e:
                    raise RepoIngestError(url, cause=e) from e

            if is_update:
                storage.swap_docs(staging_name, name)
                # swap_docs moves docs but may leave the staging project shell;
                # delete it so _staging_* entries don't accumulate.
                try:
                    if storage.project_exists(staging_name):
                        storage.delete_project(staging_name)
                except Exception:
                    pass  # Swap succeeded; orphaned staging shell is harmless

        except Exception:
            try:
                if is_update:
                    if storage.project_exists(staging_name):
                        storage.delete_project(staging_name)
                else:
                    if storage.project_exists(name):
                        storage.delete_project(name)
                    if not is_local:
                        self.delete_repo(name)
            except Exception:
                pass  # Cleanup failure must not mask the original error
            raise

        # Save metadata — failure here must not mask a successful ingest.
        try:
            sha = self.get_sha_from_path(repo_path)
            if sha:
                self.save_sha(name, sha)

            if self.is_local_path(url):
                save_url = str(Path(url).expanduser().resolve())
            else:
                save_url = url
            self.save_source_url(name, save_url)

            if path is not None:
                self.save_path(name, path)
        except Exception as exc:
            logger.warning("Failed to save repo metadata for '%s': %s", name, exc)

        return IngestResult(
            files_ingested=files_ingested,
            files_skipped=files_skipped,
            warnings=warnings,
        )
