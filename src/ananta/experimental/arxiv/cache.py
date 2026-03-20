"""Local disk cache for downloaded arXiv papers."""

from __future__ import annotations

import json
from pathlib import Path

from shesha.experimental.arxiv.models import PaperMeta


class PaperCache:
    """Cache downloaded papers to avoid re-downloading from arXiv."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def has(self, arxiv_id: str) -> bool:
        """Check if a paper is cached."""
        meta_path = self._paper_dir(arxiv_id) / "meta.json"
        return meta_path.exists()

    def store_meta(self, meta: PaperMeta) -> None:
        """Store paper metadata."""
        paper_dir = self._paper_dir(meta.arxiv_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        meta_path = paper_dir / "meta.json"
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2))

    def get_meta(self, arxiv_id: str) -> PaperMeta | None:
        """Retrieve paper metadata, or None if not cached."""
        meta_path = self._paper_dir(arxiv_id) / "meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        return PaperMeta.from_dict(data)

    def store_source_files(self, arxiv_id: str, files: dict[str, str]) -> None:
        """Store extracted LaTeX source files.

        Filenames are validated to prevent directory traversal: absolute paths
        and ``..`` components are silently skipped since they may appear in
        malicious tar archives.
        """
        source_dir = self._paper_dir(arxiv_id) / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        resolved_source = source_dir.resolve()
        for filename, content in files.items():
            file_path = (source_dir / filename).resolve()
            if not file_path.is_relative_to(resolved_source):
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

    def get_source_files(self, arxiv_id: str) -> dict[str, str] | None:
        """Retrieve source files, or None if not available."""
        source_dir = self._paper_dir(arxiv_id) / "source"
        if not source_dir.exists():
            return None
        files = {}
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(source_dir).as_posix()
                files[relative] = file_path.read_text()
        return files

    def store_pdf(self, arxiv_id: str, content: bytes) -> None:
        """Store a downloaded PDF."""
        paper_dir = self._paper_dir(arxiv_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "paper.pdf").write_bytes(content)

    def get_pdf_path(self, arxiv_id: str) -> Path | None:
        """Get path to cached PDF, or None if not available."""
        pdf_path = self._paper_dir(arxiv_id) / "paper.pdf"
        return pdf_path if pdf_path.exists() else None

    def list_papers(self) -> list[str]:
        """List all cached paper arXiv IDs."""
        if not self._cache_dir.exists():
            return []
        return sorted(
            d.name for d in self._cache_dir.iterdir() if d.is_dir() and (d / "meta.json").exists()
        )

    def _paper_dir(self, arxiv_id: str) -> Path:
        """Get the cache directory for a specific paper."""
        return self._cache_dir / arxiv_id
