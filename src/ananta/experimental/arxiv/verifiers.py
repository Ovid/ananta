"""External citation verifiers (CrossRef, OpenAlex, Semantic Scholar)."""

from __future__ import annotations

import logging

import httpx
import litellm

from shesha.experimental.arxiv.citations import ArxivVerifier, title_similarity
from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)
from shesha.experimental.arxiv.rate_limit import RateLimiter

# Thresholds for fuzzy title matching
MATCH_THRESHOLD = 0.85  # Above this = confident match
NO_MATCH_THRESHOLD = 0.50  # Below this = no match

_REQUEST_TIMEOUT = 15.0


class CrossRefVerifier:
    """Verify citations using the CrossRef API."""

    def __init__(self, polite_email: str | None = None) -> None:
        self._email = polite_email
        self._limiter = RateLimiter(min_interval=0.5 if polite_email else 1.0)

    def _headers(self) -> dict[str, str]:
        ua = "shesha-citation-checker/1.0"
        if self._email:
            ua += f" (mailto:{self._email})"
        return {"User-Agent": ua}

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via CrossRef (by DOI or title search)."""
        if citation.doi:
            return self._verify_by_doi(citation)
        if citation.title:
            return self._verify_by_title(citation)
        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No DOI or title to search",
        )

    def _verify_by_doi(self, citation: ExtractedCitation) -> VerificationResult:
        try:
            self._limiter.wait()
            resp = httpx.get(
                f"https://api.crossref.org/works/{citation.doi}",
                headers=self._headers(),
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef API request failed",
            )

        if resp.status_code == 404:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.NOT_FOUND,
                message=f"DOI {citation.doi} not found on CrossRef",
                severity="error",
            )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            self._limiter.backoff(retry_after=retry_after)
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef rate limited, will retry later",
            )
        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"CrossRef returned status {resp.status_code}",
            )

        data = resp.json().get("message", {})
        found_titles = data.get("title", [])
        found_title = found_titles[0] if found_titles else None

        if citation.title and found_title:
            sim = title_similarity(citation.title, found_title)
            if sim >= MATCH_THRESHOLD:
                return VerificationResult(
                    citation_key=citation.key,
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="crossref",
                    actual_title=found_title,
                )
            if sim < NO_MATCH_THRESHOLD:
                return VerificationResult(
                    citation_key=citation.key,
                    status=VerificationStatus.MISMATCH,
                    message=f'Cites "{citation.title}" but DOI resolves to "{found_title}"',
                    actual_title=found_title,
                    severity="warning",
                    source="crossref",
                )
            # Ambiguous (0.50-0.85)
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="crossref",
                actual_title=found_title,
                message=f"Title match ambiguous (similarity={sim:.2f})",
            )

        # DOI exists but no title to compare
        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="crossref",
        )

    def _verify_by_title(self, citation: ExtractedCitation) -> VerificationResult:
        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.crossref.org/works",
                params={"query.title": citation.title, "rows": "3"},
                headers=self._headers(),
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef title search failed",
            )

        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"CrossRef returned status {resp.status_code}",
            )

        items = resp.json().get("message", {}).get("items", [])
        for item in items:
            found_titles = item.get("title", [])
            found_title = found_titles[0] if found_titles else None
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="crossref",
                        actual_title=found_title,
                    )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on CrossRef",
        )


class OpenAlexVerifier:
    """Verify citations using the OpenAlex API."""

    def __init__(self, polite_email: str | None = None) -> None:
        self._email = polite_email
        self._limiter = RateLimiter(min_interval=0.5 if polite_email else 1.0)

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via OpenAlex title search."""
        if not citation.title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="No title to search",
            )

        params: dict[str, str] = {"search": citation.title, "per_page": "3"}
        if self._email:
            params["mailto"] = self._email

        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.openalex.org/works",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="OpenAlex API request failed",
            )

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            self._limiter.backoff(retry_after=retry_after)
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="OpenAlex rate limited, will retry later",
            )
        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"OpenAlex returned status {resp.status_code}",
            )

        results = resp.json().get("results", [])
        best_sim = 0.0
        best_title: str | None = None
        for item in results:
            found_title = item.get("title")
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="openalex",
                        actual_title=found_title,
                    )
                if sim > best_sim:
                    best_sim = sim
                    best_title = found_title

        if best_sim >= NO_MATCH_THRESHOLD and best_title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="openalex",
                actual_title=best_title,
                message=f"Title match ambiguous (similarity={best_sim:.2f})",
            )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on OpenAlex",
        )


class SemanticScholarVerifier:
    """Verify citations using the Semantic Scholar API."""

    def __init__(self) -> None:
        self._limiter = RateLimiter(min_interval=1.0)

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via Semantic Scholar title search."""
        if not citation.title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="No title to search",
            )

        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": citation.title, "limit": "3", "fields": "title"},
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="Semantic Scholar API request failed",
            )

        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"Semantic Scholar returned status {resp.status_code}",
            )

        results = resp.json().get("data", [])
        best_sim = 0.0
        best_title: str | None = None
        for item in results:
            found_title = item.get("title")
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="semantic_scholar",
                        actual_title=found_title,
                    )
                if sim > best_sim:
                    best_sim = sim
                    best_title = found_title

        if best_sim >= NO_MATCH_THRESHOLD and best_title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="semantic_scholar",
                actual_title=best_title,
                message=f"Title match ambiguous (similarity={best_sim:.2f})",
            )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on Semantic Scholar",
        )


logger = logging.getLogger(__name__)


def _llm_title_judgment(
    cited_title: str,
    found_title: str,
    found_abstract: str | None,
    model: str,
    api_key: str | None = None,
) -> bool:
    """Ask the LLM whether two titles refer to the same paper.

    Only called for ambiguous fuzzy matches (similarity 0.50-0.85).
    Returns True if the LLM judges them to be the same paper.
    """
    abstract_line = f'\nFound abstract: "{found_abstract}"' if found_abstract else ""
    prompt = (
        f'Cited title: "{cited_title}"\n'
        f'Found title: "{found_title}"{abstract_line}\n\n'
        "Are these the same paper? Respond YES or NO with a one-sentence reason."
    )
    try:
        call_kwargs: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "drop_params": True,
        }
        if api_key:
            call_kwargs["api_key"] = api_key
        response = litellm.completion(**call_kwargs)
        content = (response.choices[0].message.content or "").strip().upper()
        return content.startswith("YES")
    except Exception:
        logger.warning("LLM title judgment failed", exc_info=True)
        return False


class CascadingVerifier:
    """Orchestrates verification across multiple sources."""

    def __init__(
        self,
        *,
        arxiv_verifier: ArxivVerifier | None = None,
        crossref_verifier: CrossRefVerifier | None = None,
        openalex_verifier: OpenAlexVerifier | None = None,
        semantic_scholar_verifier: SemanticScholarVerifier | None = None,
        polite_email: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._arxiv = arxiv_verifier
        self._crossref = crossref_verifier
        self._openalex = openalex_verifier
        self._s2 = semantic_scholar_verifier
        self._model = model
        self._api_key = api_key

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify citation using cascading sources."""
        # 1. arXiv ID -> ArxivVerifier
        if citation.arxiv_id and self._arxiv:
            result = self._arxiv.verify(citation)
            if result.status not in (
                VerificationStatus.NOT_FOUND,
                VerificationStatus.UNRESOLVED,
            ):
                return result

        # 2. DOI -> CrossRefVerifier
        if citation.doi and self._crossref:
            result = self._crossref.verify(citation)
            if result.status not in (VerificationStatus.UNRESOLVED,):
                return result

        # 3. Title search chain: OpenAlex -> Semantic Scholar -> CrossRef title
        if citation.title:
            for verifier in [self._openalex, self._s2, self._crossref]:
                if verifier is None:
                    continue
                # Skip CrossRef if we already tried it via DOI
                if verifier is self._crossref and citation.doi:
                    continue
                result = verifier.verify(citation)
                if result.status in (
                    VerificationStatus.VERIFIED_EXTERNAL,
                    VerificationStatus.MISMATCH,
                ):
                    return result
                # Ambiguous match (0.50-0.85) -- try LLM judgment
                if (
                    result.status == VerificationStatus.UNRESOLVED
                    and result.actual_title
                    and result.message
                    and "ambiguous" in result.message.lower()
                    and self._model
                    and citation.title
                ):
                    is_same = _llm_title_judgment(
                        cited_title=citation.title,
                        found_title=result.actual_title,
                        found_abstract=None,
                        model=self._model,
                        api_key=self._api_key,
                    )
                    if is_same:
                        return VerificationResult(
                            citation_key=citation.key,
                            status=VerificationStatus.VERIFIED_EXTERNAL,
                            source=result.source,
                            actual_title=result.actual_title,
                            message="Verified by LLM title judgment",
                        )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="Could not verify in any database",
        )
