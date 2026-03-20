"""Download arXiv papers (source first, PDF fallback)."""

from __future__ import annotations

import gzip
import io
import tarfile
import urllib.request
from pathlib import Path
from urllib.error import URLError

from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.models import PaperMeta
from shesha.experimental.arxiv.rate_limit import RateLimiter
from shesha.models import ParsedDocument

# File extensions to extract from LaTeX source archives
TEXT_EXTENSIONS = {".tex", ".bib", ".bbl", ".bst", ".sty", ".cls", ".txt", ".md"}

# Shared rate limiter for arXiv downloads (3s between requests, thread-safe via internal lock)
_arxiv_limiter = RateLimiter(min_interval=3.0)

# Timeout for HTTP requests to arXiv (seconds)
REQUEST_TIMEOUT_SECONDS = 30


def extract_source_files(data: bytes) -> dict[str, str]:
    """Extract text files from a tar.gz or gzipped .tex file."""
    files: dict[str, str] = {}
    try:
        # Try as tarball first
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                suffix = Path(member.name).suffix.lower()
                if suffix not in TEXT_EXTENSIONS:
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                try:
                    content = f.read().decode("utf-8", errors="replace")
                    files[member.name] = content
                finally:
                    f.close()
    except tarfile.TarError:
        # Not a tarball -- try as gzipped single file
        try:
            content = gzip.decompress(data).decode("utf-8", errors="replace")
            files["main.tex"] = content
        except (gzip.BadGzipFile, UnicodeDecodeError):
            pass  # Neither tarball nor gzipped tex -- no source available
    return files


def to_parsed_document(arxiv_id: str, cache: PaperCache) -> ParsedDocument:
    """Convert a cached paper to a Shesha ParsedDocument."""
    meta = cache.get_meta(arxiv_id)
    if meta is None:
        msg = f"Paper not in cache: {arxiv_id}"
        raise ValueError(msg)

    content = ""
    fmt = "text"

    source_files = cache.get_source_files(arxiv_id)
    if source_files is not None:
        # Concatenate all source files with headers
        parts = []
        for filename, file_content in sorted(source_files.items()):
            parts.append(f"--- {filename} ---\n{file_content}")
        content = "\n\n".join(parts)
        fmt = "latex"
    else:
        # Try PDF text extraction
        pdf_path = cache.get_pdf_path(arxiv_id)
        if pdf_path is not None:
            try:
                # Late import: pdfplumber is an optional dependency
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                    content = "\n\n".join(pages)
                    fmt = "pdf"
            except Exception:
                content = f"[PDF text extraction failed for {arxiv_id}]"
                fmt = "pdf"

    doc_metadata: dict[str, str | int | float | bool] = {
        "arxiv_id": meta.arxiv_id,
        "arxiv_url": meta.arxiv_url,
        "title": meta.title,
        "authors": ", ".join(meta.authors),
        "primary_category": meta.primary_category,
    }

    return ParsedDocument(
        name=arxiv_id,
        content=content,
        format=fmt,
        metadata=doc_metadata,
        char_count=len(content),
    )


def download_paper(meta: PaperMeta, cache: PaperCache) -> PaperMeta:
    """Download a paper to the cache. Returns updated meta with source_type."""
    if cache.has(meta.arxiv_id):
        existing = cache.get_meta(meta.arxiv_id)
        if existing is not None:
            return existing
        return meta

    # Try source first
    source_url = f"https://export.arxiv.org/e-print/{meta.arxiv_id}"
    _arxiv_limiter.wait()
    try:
        with urllib.request.urlopen(source_url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = response.read()
        files = extract_source_files(data)
        if files:
            meta.source_type = "latex"
            cache.store_meta(meta)
            cache.store_source_files(meta.arxiv_id, files)
            return meta
    except (URLError, TimeoutError):
        pass  # Source not available or timed out, fall back to PDF

    # Fall back to PDF
    pdf_url = f"https://export.arxiv.org/pdf/{meta.arxiv_id}"
    _arxiv_limiter.wait()
    try:
        with urllib.request.urlopen(pdf_url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            pdf_data = response.read()
        meta.source_type = "pdf"
        cache.store_meta(meta)
        cache.store_pdf(meta.arxiv_id, pdf_data)
    except (URLError, TimeoutError):
        # Neither available -- store meta only
        meta.source_type = None
        cache.store_meta(meta)

    return meta
