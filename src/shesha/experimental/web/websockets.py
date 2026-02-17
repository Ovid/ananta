"""WebSocket handlers for query execution and citation checking.

Delegates generic query/cancel dispatch to the shared WebSocket handler and
registers arxiv-specific citation checking as an extra handler.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket

from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.citations import (
    ArxivVerifier,
    detect_llm_phrases,
    extract_citations_from_bbl,
    extract_citations_from_bib,
    extract_citations_from_text,
    format_check_report_json,
)
from shesha.experimental.arxiv.models import (
    CheckReport,
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)
from shesha.experimental.arxiv.relevance import check_topical_relevance
from shesha.experimental.arxiv.verifiers import (
    CascadingVerifier,
    CrossRefVerifier,
    OpenAlexVerifier,
    SemanticScholarVerifier,
)
from shesha.experimental.shared.websockets import websocket_handler as shared_ws_handler
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.session import WebConversationSession
from shesha.models import ParsedDocument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Citation instruction context builder
# ---------------------------------------------------------------------------


def build_citation_instructions(paper_ids: list[str], cache: PaperCache) -> str:
    """Build citation instruction text to append to user questions.

    Tells the LLM to cite papers using [@arxiv:ID] format and lists
    available papers with their titles.
    """
    if not paper_ids:
        return ""

    lines = [
        "\n\nCITATION INSTRUCTIONS: When citing a source paper in your answer, "
        "use the format [@arxiv:ID] inline (e.g. [@arxiv:2005.09008v1]). "
        "Use exactly one arxiv ID per tag. "
        "To cite multiple papers, use adjacent tags: [@arxiv:ID1][@arxiv:ID2] "
        "(NEVER [@arxiv:ID1; @arxiv:ID2]). "
        "Available papers:",
    ]
    for pid in paper_ids:
        meta = cache.get_meta(pid)
        title = meta.title if meta else pid
        lines.append(f'- [@arxiv:{pid}] "{title}"')
    lines.append("Always use [@arxiv:ID] when referencing a specific paper's claims or quotes.")

    return "\n".join(lines)


def _build_arxiv_context(
    document_ids: list[str], state: Any, loaded_docs: list[ParsedDocument]
) -> str:
    """Build context callback for the shared handler.

    Appends citation instructions using the arxiv paper cache.
    """
    return build_citation_instructions(document_ids, state.cache)


# ---------------------------------------------------------------------------
# Citation check handler (registered as extra_handler)
# ---------------------------------------------------------------------------


async def _handle_check_citations(ws: WebSocket, data: dict[str, object], state: Any) -> None:
    """Check citations for selected papers and stream progress."""
    topic = str(data.get("topic", ""))
    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    paper_ids = data.get("paper_ids")
    if not paper_ids or not isinstance(paper_ids, list) or len(paper_ids) == 0:
        await ws.send_json(
            {"type": "error", "message": "Please select one or more papers to check"}
        )
        return

    polite_email = data.get("polite_email")
    email_str = str(polite_email) if polite_email else None

    loop = asyncio.get_running_loop()
    api_key = state.shesha._config.api_key
    verifier = CascadingVerifier(
        arxiv_verifier=ArxivVerifier(searcher=state.searcher),
        crossref_verifier=CrossRefVerifier(polite_email=email_str),
        openalex_verifier=OpenAlexVerifier(polite_email=email_str),
        semantic_scholar_verifier=SemanticScholarVerifier(),
        polite_email=email_str,
        model=state.model,
        api_key=api_key,
    )
    total = len(paper_ids)
    all_papers: list[dict[str, object]] = []

    for idx, pid in enumerate(paper_ids, 1):
        await ws.send_json(
            {
                "type": "citation_progress",
                "current": idx,
                "total": total,
                "phase": "Verifying citations...",
            }
        )

        def _send_citation_progress(
            current_citation: int, total_citations: int, _idx: int = idx
        ) -> None:
            """Send per-citation progress from worker thread."""
            asyncio.run_coroutine_threadsafe(
                ws.send_json(
                    {
                        "type": "citation_progress",
                        "current": _idx,
                        "total": total,
                        "phase": f"Checking citation {current_citation}/{total_citations}...",
                    }
                ),
                loop,
            )

        paper_json = await loop.run_in_executor(
            None,
            functools.partial(
                _check_single_paper,
                str(pid),
                state,
                verifier,
                project_id,
                state.model,
                progress_callback=_send_citation_progress,
            ),
        )
        if paper_json is not None:
            all_papers.append(paper_json)

    await ws.send_json({"type": "citation_report", "papers": all_papers})


def _check_single_paper(
    paper_id: str,
    state: AppState,
    verifier: CascadingVerifier,
    project_id: str,
    model: str,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, object] | None:
    """Check citations for a single paper. Returns JSON-serializable dict or None."""
    meta = state.cache.get_meta(paper_id)
    if meta is None:
        return None

    citations: list[ExtractedCitation] = []
    source_files = state.cache.get_source_files(paper_id)
    full_text = ""

    if source_files is not None:
        for filename, content in source_files.items():
            full_text += content + "\n"
            if filename.endswith(".bib"):
                citations.extend(extract_citations_from_bib(content))
            elif filename.endswith(".bbl"):
                citations.extend(extract_citations_from_bbl(content))
    else:
        try:
            doc = state.topic_mgr._storage.get_document(project_id, paper_id)
            full_text = doc.content
            citations.extend(extract_citations_from_text(full_text))
        except Exception:
            full_text = ""  # Document may have been removed; proceed with empty text

    llm_phrases = detect_llm_phrases(full_text)
    total_citations = len(citations)
    results: list[VerificationResult] = []
    for i, c in enumerate(citations, 1):
        if progress_callback and total_citations > 1:
            progress_callback(i, total_citations)
        results.append(verifier.verify(c))

    # Topical relevance check on verified citations
    verified_keys = {
        r.citation_key
        for r in results
        if r.status in (VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_EXTERNAL)
    }
    relevance_results = check_topical_relevance(
        paper_title=meta.title,
        paper_abstract=getattr(meta, "abstract", "") or "",
        citations=citations,
        verified_keys=verified_keys,
        model=model,
        api_key=state.shesha._config.api_key,
    )
    results.extend(relevance_results)

    report = CheckReport(
        arxiv_id=meta.arxiv_id,
        title=meta.title,
        citations=citations,
        verification_results=results,
        llm_phrases=llm_phrases,
    )
    return format_check_report_json(report)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def websocket_handler(ws: WebSocket, state: AppState) -> None:
    """Handle WebSocket connections for queries and citation checks."""
    await shared_ws_handler(
        ws,
        state,
        extra_handlers={"check_citations": _handle_check_citations},
        build_context=_build_arxiv_context,
        session_factory=WebConversationSession,
    )
