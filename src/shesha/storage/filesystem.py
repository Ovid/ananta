"""Filesystem-based storage backend."""

import json
import shutil
from pathlib import Path

from shesha.exceptions import (
    DocumentNotFoundError,
    ProjectExistsError,
    ProjectNotFoundError,
)
from shesha.models import (
    AnalysisComponent,
    AnalysisExternalDep,
    ParsedDocument,
    RepoAnalysis,
    coerce_to_str,
    coerce_to_str_list,
)
from shesha.security.paths import safe_path


class FilesystemStorage:
    """Store projects and documents on the local filesystem."""

    def __init__(self, root_path: Path | str, keep_raw_files: bool = False) -> None:
        """Initialize storage with a root directory."""
        self.root = Path(root_path)
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.keep_raw_files = keep_raw_files

    def _project_path(self, project_id: str) -> Path:
        """Get the path for a project directory."""
        return safe_path(self.projects_dir, project_id)

    def get_project_dir(self, project_id: str) -> Path:
        """Get the root directory for a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        return self._project_path(project_id)

    def create_project(self, project_id: str) -> None:
        """Create a new project."""
        project_path = self._project_path(project_id)
        if project_path.exists():
            raise ProjectExistsError(project_id)
        project_path.mkdir()
        (project_path / "docs").mkdir()
        if self.keep_raw_files:
            (project_path / "raw").mkdir()
        # Write project metadata
        meta = {"id": project_id, "created": True}
        (project_path / "_meta.json").write_text(json.dumps(meta))

    def delete_project(self, project_id: str) -> None:
        """Delete a project and all its documents."""
        project_path = self._project_path(project_id)
        if project_path.exists():
            shutil.rmtree(project_path)

    def list_projects(self) -> list[str]:
        """List all project IDs."""
        if not self.projects_dir.exists():
            return []
        return [
            p.name
            for p in self.projects_dir.iterdir()
            if p.is_dir() and (p / "_meta.json").exists()
        ]

    def project_exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        project_path = self._project_path(project_id)
        return project_path.exists() and (project_path / "_meta.json").exists()

    def store_document(
        self, project_id: str, doc: ParsedDocument, raw_path: Path | None = None
    ) -> None:
        """Store a parsed document in a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        docs_dir = self._project_path(project_id) / "docs"
        doc_path = safe_path(docs_dir, f"{doc.name}.json")
        # Create parent directories for nested paths (e.g., src/main.py.json)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_data = {
            "name": doc.name,
            "content": doc.content,
            "format": doc.format,
            "metadata": doc.metadata,
            "char_count": doc.char_count,
            "parse_warnings": doc.parse_warnings,
        }
        doc_path.write_text(json.dumps(doc_data, indent=2))

        # Store raw file if enabled and path provided
        if self.keep_raw_files and raw_path is not None:
            raw_dir = self._project_path(project_id) / "raw"
            raw_dir.mkdir(exist_ok=True)
            raw_dest = safe_path(raw_dir, doc.name)
            raw_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_path, raw_dest)

    def get_document(self, project_id: str, doc_name: str) -> ParsedDocument:
        """Retrieve a document by name."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        docs_dir = self._project_path(project_id) / "docs"
        doc_path = safe_path(docs_dir, f"{doc_name}.json")
        if not doc_path.exists():
            raise DocumentNotFoundError(project_id, doc_name)
        doc_data = json.loads(doc_path.read_text())
        return ParsedDocument(**doc_data)

    def list_documents(self, project_id: str) -> list[str]:
        """List all document names in a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        docs_dir = self._project_path(project_id) / "docs"
        # Use rglob to find nested documents (e.g., src/main.py.json)
        # Return the relative path without the .json extension
        doc_names = []
        for p in docs_dir.rglob("*.json"):
            rel_path = p.relative_to(docs_dir)
            # Remove the .json extension to get the document name
            doc_name = str(rel_path)[:-5]  # Remove ".json"
            doc_names.append(doc_name)
        return doc_names

    def delete_document(self, project_id: str, doc_name: str) -> None:
        """Delete a document from a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        docs_dir = self._project_path(project_id) / "docs"
        doc_path = safe_path(docs_dir, f"{doc_name}.json")
        if doc_path.exists():
            doc_path.unlink()

    def load_all_documents(self, project_id: str) -> list[ParsedDocument]:
        """Load all documents in a project for querying."""
        doc_names = self.list_documents(project_id)
        return [self.get_document(project_id, name) for name in doc_names]

    def get_traces_dir(self, project_id: str) -> Path:
        """Get the traces directory for a project, creating it if needed."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        traces_dir = self._project_path(project_id) / "traces"
        traces_dir.mkdir(exist_ok=True)
        return traces_dir

    def list_traces(self, project_id: str) -> list[Path]:
        """List all trace files in a project, sorted by name (oldest first)."""
        traces_dir = self.get_traces_dir(project_id)
        traces = list(traces_dir.glob("*.jsonl"))
        return sorted(traces, key=lambda p: p.name)

    def store_analysis(self, project_id: str, analysis: RepoAnalysis) -> None:
        """Store a codebase analysis for a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        project_path = self._project_path(project_id)
        analysis_path = project_path / "_analysis.json"
        analysis_data = {
            "version": analysis.version,
            "generated_at": analysis.generated_at,
            "head_sha": analysis.head_sha,
            "overview": analysis.overview,
            "caveats": analysis.caveats,
            "components": [
                {
                    "name": c.name,
                    "path": c.path,
                    "description": c.description,
                    "apis": c.apis,
                    "models": c.models,
                    "entry_points": c.entry_points,
                    "internal_dependencies": c.internal_dependencies,
                    "auth": c.auth,
                    "data_persistence": c.data_persistence,
                }
                for c in analysis.components
            ],
            "external_dependencies": [
                {
                    "name": d.name,
                    "type": d.type,
                    "description": d.description,
                    "used_by": d.used_by,
                    "optional": d.optional,
                }
                for d in analysis.external_dependencies
            ],
        }
        analysis_path.write_text(json.dumps(analysis_data, indent=2))

    def load_analysis(self, project_id: str) -> RepoAnalysis | None:
        """Load a codebase analysis for a project, or None if not present."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        project_path = self._project_path(project_id)
        analysis_path = project_path / "_analysis.json"
        if not analysis_path.exists():
            return None
        data = json.loads(analysis_path.read_text())
        components = [
            AnalysisComponent(
                name=coerce_to_str(c["name"]),
                path=coerce_to_str(c["path"]),
                description=coerce_to_str(c["description"]),
                apis=c["apis"],
                models=coerce_to_str_list(c["models"]),
                entry_points=coerce_to_str_list(c["entry_points"]),
                internal_dependencies=coerce_to_str_list(c["internal_dependencies"]),
                auth=c.get("auth"),
                data_persistence=c.get("data_persistence"),
            )
            for c in data["components"]
        ]
        external_deps = [
            AnalysisExternalDep(
                name=coerce_to_str(d["name"]),
                type=coerce_to_str(d["type"]),
                description=coerce_to_str(d["description"]),
                used_by=coerce_to_str_list(d["used_by"]),
                optional=d.get("optional", False),
            )
            for d in data["external_dependencies"]
        ]
        raw_caveats = data.get("caveats")
        caveats = coerce_to_str(raw_caveats) if raw_caveats is not None else None
        return RepoAnalysis(
            version=data["version"],
            generated_at=data["generated_at"],
            head_sha=data["head_sha"],
            overview=coerce_to_str(data["overview"]),
            components=components,
            external_dependencies=external_deps,
            **({"caveats": caveats} if caveats is not None else {}),
        )

    def swap_docs(self, source_project_id: str, target_project_id: str) -> None:
        """Atomically replace target project's docs with source project's docs.

        Uses rename-based swap with rollback on failure:
        1. Rename target/docs → target/docs_backup
        2. Rename source/docs → target/docs
        3. Delete backup

        If step 2 fails, restores backup to target/docs.
        """
        if not self.project_exists(source_project_id):
            raise ProjectNotFoundError(source_project_id)
        if not self.project_exists(target_project_id):
            raise ProjectNotFoundError(target_project_id)

        source_docs = self._project_path(source_project_id) / "docs"
        target_docs = self._project_path(target_project_id) / "docs"
        backup_docs = self._project_path(target_project_id) / "docs_backup"

        # Recover from a prior crashed swap (if any).
        if backup_docs.exists():
            if not target_docs.exists():
                # Crash between step 1 and 2: backup has the only copy.
                # Restore it so the swap can proceed normally.
                backup_docs.rename(target_docs)
            else:
                # Crash after step 2: target/docs has the new data,
                # backup is stale. Must delete so step 1 rename can proceed.
                shutil.rmtree(backup_docs)

        # Step 1: Move target docs to backup (atomic on same filesystem)
        target_docs.rename(backup_docs)

        try:
            # Step 2: Move source docs to target (atomic on same filesystem)
            source_docs.rename(target_docs)
        except Exception:
            # Restore backup on failure
            backup_docs.rename(target_docs)
            raise

        # Step 3: Remove backup (best-effort; next call recovers if this fails)
        try:
            shutil.rmtree(backup_docs)
        except OSError:
            pass  # Leftover backup will be cleaned up on next swap

    def delete_analysis(self, project_id: str) -> None:
        """Delete the codebase analysis for a project."""
        if not self.project_exists(project_id):
            raise ProjectNotFoundError(project_id)
        project_path = self._project_path(project_id)
        analysis_path = project_path / "_analysis.json"
        if analysis_path.exists():
            analysis_path.unlink()
