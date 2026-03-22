"""arXiv search wrapper with pagination."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import arxiv

from ananta.explorers.arxiv.papers.models import PaperMeta


def extract_arxiv_id(entry_id: str) -> str:
    """Extract the arXiv ID from an entry_id URL.

    Old-style arXiv IDs (e.g. cs/9808001v1) contain slashes which break
    document ID validation and create subdirectories in storage.  Replace
    the slash with a hyphen so the ID is safe for both.
    """
    # entry_id looks like "http://arxiv.org/abs/2501.12345v1"
    match = re.search(r"/abs/(.+)$", entry_id)
    if match:
        return match.group(1).replace("/", "-")
    return entry_id


def _extract_raw_arxiv_id(entry_id: str) -> str:
    """Extract the raw arXiv ID preserving slashes (for URL construction)."""
    match = re.search(r"/abs/(.+)$", entry_id)
    if match:
        return match.group(1)
    return entry_id


def _result_to_meta(result: arxiv.Result) -> PaperMeta:
    """Convert an arxiv.Result to our PaperMeta model."""
    arxiv_id = extract_arxiv_id(result.entry_id)
    raw_id = _extract_raw_arxiv_id(result.entry_id)
    return PaperMeta(
        arxiv_id=arxiv_id,
        title=result.title,
        authors=[a.name for a in result.authors],
        abstract=result.summary,
        published=result.published,
        updated=result.updated,
        categories=result.categories,
        primary_category=result.primary_category,
        pdf_url=result.pdf_url or f"https://arxiv.org/pdf/{raw_id}",
        arxiv_url=f"https://arxiv.org/abs/{raw_id}",
        comment=result.comment,
        journal_ref=result.journal_ref,
        doi=result.doi,
    )


def format_result(meta: PaperMeta, index: int) -> str:
    """Format a single search result for display."""
    authors = ", ".join(meta.authors[:3])
    if len(meta.authors) > 3:
        authors += f" +{len(meta.authors) - 3} more"
    date_str = meta.published.strftime("%Y-%m-%d")
    comment_str = f" | {meta.comment}" if meta.comment else ""
    lines = [
        f'  {index}. [{meta.arxiv_id}] "{meta.title}"',
        f"     {authors} | {meta.primary_category} | {date_str}{comment_str}",
        f"     {meta.arxiv_url}",
    ]
    return "\n".join(lines)


class ArxivSearcher:
    """Search arXiv with rate-limited pagination."""

    def __init__(self, page_size: int = 10) -> None:
        self._client = arxiv.Client(
            page_size=page_size,
            delay_seconds=3.0,
            num_retries=3,
        )
        self._page_size = page_size

    def close(self) -> None:
        """Close the underlying HTTP session.

        ``requests``' ``session.close()`` drops pool references via
        ``PoolManager.clear()`` without calling ``pool.close()``, so
        pooled connections and their ``http.client.HTTPResponse`` objects
        linger until the garbage collector finalises them.  During
        interpreter shutdown the finalisation order is unpredictable and
        ``urllib3.HTTPResponse.__del__`` (inherited from ``io.IOBase``)
        can try to flush an already-closed socket.  Explicitly closing
        every pool first avoids this.
        """
        session = self._client._session
        for adapter in session.adapters.values():
            pool_manager = getattr(adapter, "poolmanager", None)
            if pool_manager is not None:
                with pool_manager.pools.lock:
                    pools = list(pool_manager.pools._container.values())
                for pool in pools:
                    pool.close()
        session.close()

    def search(
        self,
        query: str,
        *,
        author: str | None = None,
        category: str | None = None,
        recent_days: int | None = None,
        sort_by: str = "relevance",
        max_results: int = 10,
        start: int = 0,
    ) -> list[PaperMeta]:
        """Search arXiv and return results.

        Args:
            query: Keyword search string.
            author: Filter by author name.
            category: Filter by arXiv category (e.g., "cs.AI").
            recent_days: Only return papers from the last N days.
            sort_by: Sort order — "relevance", "date", or "updated".
            max_results: Maximum results to return.
            start: Offset for pagination (0-based).
        """
        parts = []
        # Treat "*" as "no keyword filter" — arxiv rejects literal all:*
        if query and query.strip() != "*":
            parts.append(f"all:{query}")
        if author:
            parts.append(f"au:{author}")
        if category:
            parts.append(f"cat:{category}")
        if recent_days is not None:
            now = datetime.now(tz=UTC)
            start_date = now - timedelta(days=recent_days)
            # arXiv date format: YYYYMMDDTTTT
            date_from = start_date.strftime("%Y%m%d0000")
            date_to = now.strftime("%Y%m%d2359")
            parts.append(f"submittedDate:[{date_from}+TO+{date_to}]")
        if not parts:
            raise ValueError("At least one search criteria is required")
        full_query = " AND ".join(parts)

        sort_criterion = {
            "relevance": arxiv.SortCriterion.Relevance,
            "date": arxiv.SortCriterion.SubmittedDate,
            "updated": arxiv.SortCriterion.LastUpdatedDate,
        }.get(sort_by, arxiv.SortCriterion.Relevance)

        search = arxiv.Search(
            query=full_query,
            max_results=max_results + start,
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending,
        )
        results = list(self._client.results(search, offset=start))
        return [_result_to_meta(r) for r in results]

    def get_by_id(self, arxiv_id: str) -> PaperMeta | None:
        """Fetch metadata for a specific arXiv ID."""
        search = arxiv.Search(id_list=[arxiv_id])
        try:
            results = list(self._client.results(search))
        except Exception:
            return None  # Invalid ID or network error
        if not results:
            return None
        return _result_to_meta(results[0])
