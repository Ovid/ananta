"""Topical relevance checking via LLM."""

from __future__ import annotations

import json
import logging

import litellm

from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


def check_topical_relevance(
    *,
    paper_title: str,
    paper_abstract: str,
    citations: list[ExtractedCitation],
    verified_keys: set[str],
    model: str,
    api_key: str | None = None,
) -> list[VerificationResult]:
    """Check topical relevance of verified citations using the LLM.

    Returns VerificationResult entries only for citations flagged as unrelated.
    """
    to_check = [c for c in citations if c.key in verified_keys and c.title]
    if not to_check:
        return []

    citation_list = "\n".join(
        f'{i + 1}. key: "{c.key}", title: "{c.title}"' for i, c in enumerate(to_check)
    )

    prompt = f"""Paper title: "{paper_title}"
Paper abstract: "{paper_abstract}"

For each citation below, determine whether it is topically relevant to this paper.
Be generous — interdisciplinary citations are legitimate. Only flag citations that
are clearly unrelated to the paper's subject matter.

Respond with a JSON array of objects with "key" (string), "relevant" (boolean),
and "reason" (one sentence). No other text.

Citations:
{citation_list}"""

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
        content = response.choices[0].message.content
        if not content:
            return []

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        items = json.loads(content)
    except Exception:
        logger.warning("Topical relevance check failed", exc_info=True)
        return []

    results = []
    for item in items:
        if not item.get("relevant", True):
            key = item.get("key", "")
            reason = item.get("reason", "Flagged as topically unrelated")
            results.append(
                VerificationResult(
                    citation_key=key,
                    status=VerificationStatus.TOPICALLY_UNRELATED,
                    message=reason,
                    severity="warning",
                )
            )

    return results
