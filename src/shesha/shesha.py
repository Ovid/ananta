"""Main Shesha class - the public API."""

import atexit
import logging
import re
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import docker
from docker.errors import DockerException

from shesha.analysis import AnalysisGenerator
from shesha.config import SheshaConfig
from shesha.exceptions import (
    ProjectNotFoundError,
    RepoError,
    RepoIngestError,
)
from shesha.models import ProjectInfo, RepoProjectResult
from shesha.parser import create_default_registry
from shesha.parser.registry import ParserRegistry
from shesha.project import Project
from shesha.repo.ingester import RepoIngester
from shesha.rlm.engine import RLMEngine
from shesha.sandbox.pool import ContainerPool
from shesha.storage.base import StorageBackend
from shesha.storage.filesystem import FilesystemStorage

if TYPE_CHECKING:
    from shesha.models import RepoAnalysis
    from shesha.parser.base import DocumentParser

logger = logging.getLogger(__name__)


class Shesha:
    """Main entry point for Shesha - Recursive Language Models."""

    def __init__(
        self,
        model: str | None = None,
        storage_path: str | Path | None = None,
        api_key: str | None = None,
        pool_size: int | None = None,
        config: SheshaConfig | None = None,
        storage: StorageBackend | None = None,
        engine: RLMEngine | None = None,
        parser_registry: ParserRegistry | None = None,
        repo_ingester: RepoIngester | None = None,
    ) -> None:
        """Initialize Shesha.

        Does not require Docker. Docker availability is checked lazily
        when start() is called, allowing ingest-only workflows without
        a Docker daemon.

        Components can be injected for testing or extensibility:
            storage: Custom StorageBackend (default: FilesystemStorage)
            engine: Custom RLMEngine (default: created from config)
            parser_registry: Custom ParserRegistry (default: all built-in parsers)
            repo_ingester: Custom RepoIngester (default: created from config)
        """
        # Use provided config or create from args
        if config is None:
            config = SheshaConfig.load()
        if model is not None:
            config.model = model
        if storage_path is not None:
            config.storage_path = str(storage_path)
        if api_key is not None:
            config.api_key = api_key
        if pool_size is not None:
            config.pool_size = pool_size

        self._config = config

        # Initialize components (use injected or create defaults)
        self._storage: StorageBackend = storage or FilesystemStorage(
            config.storage_path,
            keep_raw_files=config.keep_raw_files,
        )
        self._parser_registry = parser_registry or create_default_registry()

        # Pool is created lazily in start()
        self._pool: ContainerPool | None = None

        # Create RLM engine (pool set later in start())
        self._rlm_engine = engine or RLMEngine(
            model=config.model,
            api_key=config.api_key,
            max_iterations=config.max_iterations,
            max_output_chars=config.max_output_chars,
            execution_timeout=config.execution_timeout_sec,
            max_traces_per_project=config.max_traces_per_project,
            verify_citations=config.verify_citations,
            verify=config.verify,
        )

        # Initialize repo ingester
        self._repo_ingester = repo_ingester or RepoIngester(storage_path=config.storage_path)

        # Track if stopped to avoid double-cleanup
        self._stopped = False

        # Register cleanup on exit using weak reference
        weak_self = weakref.ref(self)

        def _cleanup() -> None:
            obj = weak_self()
            if obj is not None:
                obj.stop()

        atexit.register(_cleanup)

    @property
    def storage(self) -> StorageBackend:
        """The storage backend used by this instance."""
        return self._storage

    @staticmethod
    def _check_docker_available() -> None:
        """Verify Docker daemon is running. Raises RuntimeError if not."""
        try:
            client = docker.from_env()
            client.close()
        except DockerException as e:
            error_str = str(e)
            if "Connection refused" in error_str:
                raise RuntimeError(
                    "Docker is not running. Please start Docker Desktop and try again."
                ) from e
            if "No such file or directory" in error_str:
                raise RuntimeError(
                    "No Docker-compatible socket found. "
                    "If you're using Podman, set DOCKER_HOST to Podman's socket:\n"
                    '  export DOCKER_HOST="unix://$(podman machine inspect '
                    "--format '{{.ConnectionInfo.PodmanSocket.Path}}')\""
                ) from e
            raise

    def create_project(self, project_id: str) -> Project:
        """Create a new project."""
        self._storage.create_project(project_id)
        return Project(
            project_id=project_id,
            storage=self._storage,
            parser_registry=self._parser_registry,
            rlm_engine=self._rlm_engine,
        )

    def get_project(self, project_id: str) -> Project:
        """Get an existing project."""
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        return Project(
            project_id=project_id,
            storage=self._storage,
            parser_registry=self._parser_registry,
            rlm_engine=self._rlm_engine,
        )

    def list_projects(self) -> list[str]:
        """List all projects."""
        return self._storage.list_projects()

    def delete_project(self, project_id: str, *, cleanup_repo: bool = True) -> None:
        """Delete a project and optionally its cloned repository.

        Args:
            project_id: Project to delete.
            cleanup_repo: If True (default), also removes cloned repo data
                for remote repositories. Has no effect for projects
                created from local paths.
        """
        if cleanup_repo:
            source_url = self._repo_ingester.get_source_url(project_id)
            if source_url and not self._repo_ingester.is_local_path(source_url):
                self._repo_ingester.delete_repo(project_id)

        self._storage.delete_project(project_id)

    def get_project_info(self, project_id: str) -> ProjectInfo:
        """Get metadata about a project.

        Args:
            project_id: ID of the project.

        Returns:
            ProjectInfo with source URL, whether it's local, source existence,
            and analysis status.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)

        source_url = self._repo_ingester.get_source_url(project_id)
        analysis_status = self.get_analysis_status(project_id)

        if source_url is None:
            return ProjectInfo(
                project_id=project_id,
                source_url=None,
                is_local=False,
                source_exists=True,
                analysis_status=analysis_status,
            )

        is_local = self._repo_ingester.is_local_path(source_url)

        if is_local:
            source_exists = Path(source_url).expanduser().exists()
        else:
            source_exists = True  # Remote repos always "exist"

        return ProjectInfo(
            project_id=project_id,
            source_url=source_url,
            is_local=is_local,
            source_exists=source_exists,
            analysis_status=analysis_status,
        )

    def get_analysis_status(self, project_id: str) -> Literal["current", "stale", "missing"]:
        """Check the status of a project's codebase analysis.

        Args:
            project_id: ID of the project.

        Returns:
            "current" if analysis exists and matches current HEAD SHA,
            "stale" if analysis exists but HEAD SHA has changed,
            "missing" if no analysis exists.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)

        analysis = self._storage.load_analysis(project_id)
        if analysis is None:
            return "missing"

        current_sha = self._repo_ingester.get_saved_sha(project_id)
        if current_sha is None:
            return "current"

        if analysis.head_sha == current_sha:
            return "current"

        return "stale"

    def get_analysis(self, project_id: str) -> "RepoAnalysis | None":
        """Get the codebase analysis for a project.

        Args:
            project_id: ID of the project.

        Returns:
            RepoAnalysis if it exists, None otherwise.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        return self._storage.load_analysis(project_id)

    def get_project_sha(self, project_id: str) -> str | None:
        """Get the saved HEAD SHA for a project.

        Args:
            project_id: ID of the project.

        Returns:
            The SHA string, or None if not available.
        """
        return self._repo_ingester.get_saved_sha(project_id)

    def generate_analysis(self, project_id: str) -> "RepoAnalysis":
        """Generate and store a codebase analysis for a project.

        Args:
            project_id: ID of the project to analyze.

        Returns:
            The generated RepoAnalysis.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)

        generator = AnalysisGenerator(
            get_project=self.get_project,
            get_project_sha=self.get_project_sha,
        )
        analysis = generator.generate(project_id)
        self._storage.store_analysis(project_id, analysis)
        return analysis

    def check_repo_for_updates(self, project_id: str) -> RepoProjectResult:
        """Check if a cloned repository has updates available.

        This retrieves the stored repository URL and checks if the remote
        has newer commits than the locally cached version.

        Args:
            project_id: ID of an existing project created from a repository.

        Returns:
            RepoProjectResult with status 'unchanged' or 'updates_available'.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
            RepoError: If project has no stored repo URL.
        """
        if not self._storage.project_exists(project_id):
            raise ProjectNotFoundError(project_id)

        url = self._repo_ingester.get_source_url(project_id)
        if not url:
            raise RepoError(
                f"No repository URL found for project '{project_id}'. "
                "This project may not have been created from a repository."
            )

        token = self._repo_ingester.resolve_token(url, None)
        return self._handle_existing_project(url, project_id, token, None)

    def register_parser(self, parser: "DocumentParser") -> None:
        """Register a custom document parser."""
        self._parser_registry.register(parser)

    def start(self) -> None:
        """Check Docker availability, create the container pool, and start it."""
        if self._pool is not None and not self._stopped:
            return
        logger.info("Starting Shesha (model=%s)", self._config.model)
        self._check_docker_available()
        self._stopped = False
        self._pool = ContainerPool(
            size=self._config.pool_size,
            image=self._config.sandbox_image,
            memory_limit=f"{self._config.container_memory_mb}m",
        )
        self._rlm_engine.set_pool(self._pool)
        self._pool.start()

    def stop(self) -> None:
        """Stop the container pool."""
        if self._stopped:
            return
        self._stopped = True
        if self._pool is not None:
            self._pool.stop()
            self._rlm_engine.set_pool(None)

    def __enter__(self) -> "Shesha":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.stop()

    def create_project_from_repo(
        self,
        url: str,
        name: str | None = None,
        token: str | None = None,
        path: str | None = None,
    ) -> RepoProjectResult:
        """Create a project from a git repository.

        Args:
            url: Git URL (HTTPS, SSH) or local path.
            name: Project name (defaults to repo name).
            token: Auth token (defaults to env var based on host).
            path: Optional subdirectory to ingest.

        Returns:
            RepoProjectResult with project and status.
        """
        if name is None:
            name = self._extract_repo_name(url)

        resolved_token = self._repo_ingester.resolve_token(url, token)

        if self._storage.project_exists(name):
            return self._handle_existing_project(url, name, resolved_token, path)

        return self._create_new_project_from_repo(url, name, resolved_token, path)

    def _extract_repo_name(self, url: str) -> str:
        """Extract repository name from URL.

        The returned name is sanitised so it only contains characters
        matching ``[a-zA-Z0-9._-]``, which keeps it compatible with the
        ``_SAFE_ID_RE`` validation used in the WS handlers.
        """
        cleaned = url.rstrip("/")
        if self._repo_ingester.is_local_path(url):
            path = Path(cleaned).expanduser().resolve()
            raw = f"{path.parent.name}-{path.name}"
        else:
            match = re.search(r"[/:]([^/]+/[^/]+?)(?:\.git)?$", cleaned)
            raw = match.group(1).replace("/", "-") if match else "unnamed-repo"
        return self._sanitize_project_id(raw)

    @staticmethod
    def _sanitize_project_id(raw: str) -> str:
        """Replace characters outside ``[a-zA-Z0-9._-]`` with hyphens.

        The result is guaranteed to match ``_SAFE_ID_RE``
        (``^[a-zA-Z0-9][a-zA-Z0-9._-]*$``).
        """
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", raw)
        sanitized = re.sub(r"-+", "-", sanitized)
        sanitized = sanitized.lstrip("._-")
        sanitized = sanitized.strip("-")
        return sanitized or "unnamed-repo"

    def _handle_existing_project(
        self,
        url: str,
        name: str,
        token: str | None,
        path: str | None,
    ) -> RepoProjectResult:
        """Handle create_project_from_repo for existing project."""
        saved_sha = self._repo_ingester.get_saved_sha(name)
        if self._repo_ingester.is_local_path(url):
            current_sha = self._repo_ingester.get_sha_from_path(Path(url).expanduser())
        else:
            current_sha = self._repo_ingester.get_remote_sha(url, token)

        project = self.get_project(name)

        if saved_sha is not None and saved_sha == current_sha:
            return RepoProjectResult(
                project=project,
                status="unchanged",
                files_ingested=len(self._storage.list_documents(name)),
            )

        def apply_updates() -> RepoProjectResult:
            if not self._repo_ingester.is_local_path(url):
                self._repo_ingester.pull(name)
            return self._ingest_repo(url, name, token, path, is_update=True)

        return RepoProjectResult(
            project=project,
            status="updates_available",
            files_ingested=len(self._storage.list_documents(name)),
            _apply_updates_fn=apply_updates,
        )

    def _create_new_project_from_repo(
        self,
        url: str,
        name: str,
        token: str | None,
        path: str | None,
    ) -> RepoProjectResult:
        """Create a new project from repo."""
        if self._repo_ingester.is_local_path(url):
            local_path = Path(url).expanduser()
            if not self._repo_ingester.is_git_repo(local_path):
                raise RepoIngestError(url, RuntimeError(f"'{url}' is not a git repository"))
        else:
            self._repo_ingester.clone(url, name, token)
        return self._ingest_repo(url, name, token, path, is_update=False)

    def _ingest_repo(
        self,
        url: str,
        name: str,
        token: str | None,
        path: str | None,
        *,
        is_update: bool,
    ) -> RepoProjectResult:
        """Ingest files from repository into project.

        Delegates to RepoIngester.ingest() for orchestration and wraps
        the result with project metadata.
        """
        result = self._repo_ingester.ingest(
            storage=self._storage,
            parser_registry=self._parser_registry,
            url=url,
            name=name,
            path=path,
            is_update=is_update,
        )

        project = self.get_project(name)
        return RepoProjectResult(
            project=project,
            status="created",
            files_ingested=result.files_ingested,
            files_skipped=result.files_skipped,
            warnings=result.warnings,
        )
