"""Tests for paper downloader."""

from __future__ import annotations

import gzip
import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from ananta.experimental.arxiv.models import PaperMeta


def _make_meta() -> PaperMeta:
    """Create a test PaperMeta instance."""
    return PaperMeta(
        arxiv_id="2501.12345",
        title="Test Paper",
        authors=["Smith, J."],
        abstract="Abstract",
        published=datetime(2025, 1, 15, tzinfo=UTC),
        updated=datetime(2025, 1, 15, tzinfo=UTC),
        categories=["cs.AI"],
        primary_category="cs.AI",
        pdf_url="https://arxiv.org/pdf/2501.12345",
        arxiv_url="https://arxiv.org/abs/2501.12345",
    )


def _make_tarball(files: dict[str, str]) -> bytes:
    """Create an in-memory tar.gz containing the given files."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _make_gzipped_tex(content: str) -> bytes:
    """Create gzipped single-file source (arXiv format for single .tex)."""
    return gzip.compress(content.encode("utf-8"))


class TestExtractTarball:
    """Tests for tarball extraction."""

    def test_extract_tex_and_bib(self) -> None:
        from ananta.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball(
            {
                "main.tex": "\\documentclass{article}\\begin{document}Hello\\end{document}",
                "refs.bib": "@article{smith2023, title={Test}}",
            }
        )
        files = extract_source_files(tarball)
        assert "main.tex" in files
        assert "refs.bib" in files
        assert "\\documentclass" in files["main.tex"]

    def test_extract_filters_non_text_files(self) -> None:
        from ananta.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball(
            {
                "main.tex": "\\documentclass{article}",
                "figure.png": "fake png data",
            }
        )
        files = extract_source_files(tarball)
        assert "main.tex" in files
        # Binary files should be excluded
        assert "figure.png" not in files

    def test_extract_bbl_file(self) -> None:
        from ananta.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball(
            {
                "main.tex": "\\documentclass{article}",
                "main.bbl": "\\begin{thebibliography}{1}\\bibitem{a} Author\\end{thebibliography}",
            }
        )
        files = extract_source_files(tarball)
        assert "main.bbl" in files

    def test_extract_single_gzipped_tex(self) -> None:
        """arXiv serves single-file submissions as gzipped .tex, not tarball."""
        from ananta.experimental.arxiv.download import extract_source_files

        content = "\\documentclass{article}\\begin{document}Hi\\end{document}"
        gz_data = _make_gzipped_tex(content)
        files = extract_source_files(gz_data)
        assert len(files) == 1
        assert any("documentclass" in v for v in files.values())


class TestToParsedDocument:
    """Tests for converting cached papers to ParsedDocument."""

    def test_latex_source_to_document(self, tmp_path: Path) -> None:
        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import to_parsed_document

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "latex"
        cache.store_meta(meta)
        cache.store_source_files(
            "2501.12345",
            {
                "main.tex": "\\documentclass{article}\\begin{document}Content here.\\end{document}",
                "refs.bib": "@article{s, title={T}}",
            },
        )
        doc = to_parsed_document("2501.12345", cache)
        assert doc.name == "2501.12345"
        assert "Content here" in doc.content
        assert doc.metadata.get("arxiv_url") == "https://arxiv.org/abs/2501.12345"

    def test_pdf_fallback_to_document(self, tmp_path: Path) -> None:
        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import to_parsed_document

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "pdf"
        cache.store_meta(meta)
        # We can't easily test real PDF extraction, so just verify it handles
        # the case where a PDF path exists
        cache.store_pdf("2501.12345", b"%PDF-1.4 fake")
        # This will fail to extract text from fake PDF -- that's OK,
        # the function should handle it gracefully
        doc = to_parsed_document("2501.12345", cache)
        assert doc.name == "2501.12345"
        assert doc.metadata.get("arxiv_url") == "https://arxiv.org/abs/2501.12345"


class TestDownloadPaper:
    """Tests for the full download flow."""

    @patch("ananta.experimental.arxiv.download.urllib.request.urlopen")
    def test_download_tries_source_first(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        # Mock source download returning a tarball
        tarball = _make_tarball({"main.tex": "\\documentclass{article}"})
        mock_response = MagicMock()
        mock_response.read.return_value = tarball
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result_meta = download_paper(meta, cache)
        assert result_meta.source_type == "latex"
        assert cache.has("2501.12345")
        assert cache.get_source_files("2501.12345") is not None

    @patch("ananta.experimental.arxiv.download.urllib.request.urlopen")
    def test_download_falls_back_to_pdf(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        from urllib.error import HTTPError

        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        # First call (source) raises 404, second call (PDF) succeeds
        pdf_response = MagicMock()
        pdf_response.read.return_value = b"%PDF-1.4 fake content"
        pdf_response.__enter__ = lambda s: s
        pdf_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None),
            pdf_response,
        ]

        result_meta = download_paper(meta, cache)
        assert result_meta.source_type == "pdf"
        assert cache.get_pdf_path("2501.12345") is not None

    @patch("ananta.experimental.arxiv.download.urllib.request.urlopen")
    def test_download_handles_timeout(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        from urllib.error import URLError

        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        # Both source and PDF requests time out
        mock_urlopen.side_effect = URLError("timed out")

        result_meta = download_paper(meta, cache)
        # Should store meta with no source_type rather than hang or crash
        assert result_meta.source_type is None
        assert cache.has("2501.12345")

    @patch("ananta.experimental.arxiv.download.urllib.request.urlopen")
    def test_urlopen_called_with_timeout(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import (
            REQUEST_TIMEOUT_SECONDS,
            download_paper,
        )

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        tarball = _make_tarball({"main.tex": "\\documentclass{article}"})
        mock_response = MagicMock()
        mock_response.read.return_value = tarball
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        download_paper(meta, cache)
        # Verify timeout was passed
        _args, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == REQUEST_TIMEOUT_SECONDS

    def test_skip_download_if_cached(self, tmp_path: Path) -> None:
        from ananta.experimental.arxiv.cache import PaperCache
        from ananta.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "latex"
        cache.store_meta(meta)

        # Should return immediately without downloading
        result = download_paper(meta, cache)
        assert result.source_type == "latex"
