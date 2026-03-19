"""Analysis shortcut — skip RLM when the pre-computed analysis can answer."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shesha.llm.client import LLMClient, LLMClientFactory
from shesha.rlm.boundary import generate_boundary, wrap_untrusted

if TYPE_CHECKING:
    from shesha.project import Project
    from shesha.rlm.engine import ProgressCallback, QueryResult


@dataclass
class ShortcutResult:
    """Result returned when the analysis shortcut answered the question."""

    answer: str
    prompt_tokens: int
    completion_tokens: int


_SYSTEM_PROMPT = """\
You are a helpful assistant. You have access to a pre-computed codebase analysis.
If the user's question can be fully and accurately answered using ONLY the
analysis below, provide a clear, complete answer.

If the question requires deeper investigation, respond with exactly: NEED_DEEPER

Respond NEED_DEEPER for ANY of these situations:
- The analysis does not contain the information needed to answer
- You would need to read specific source files, trace execution, or find bugs
- You are unsure whether the analysis fully covers the question
- The user is asking about something not mentioned in the analysis

CRITICAL: Never answer by describing what the analysis lacks or does not mention. \
"The analysis does not cover X" is NOT a valid answer — respond NEED_DEEPER instead. \
Absence of information in the analysis does not mean absence in the codebase.

Do not guess or speculate beyond what the analysis states."""

_CLASSIFIER_PROMPT = """\
You are a query classifier. Given a user question about a codebase, \
determine whether a high-level codebase summary could answer it, or whether \
it requires access to actual source files.

The summary contains ONLY:
- A 2-3 sentence overview of the project's purpose
- Major components (name, path, description, public APIs, data models, entry points)
- External dependencies (name, type, description)

It does NOT contain individual file listings, file contents, README/docs text, \
test details, CI config, or any non-component files.

Respond with exactly one word: ANALYSIS_OK or NEED_DEEPER.

NEED_DEEPER if the question involves ANY of:
  * Checking whether a specific file or artifact exists
  * Verifying accuracy or correctness of any documentation or prior answer
  * The user expressing doubt, disagreement, or correction
  * Reading, inspecting, or quoting specific file contents
  * Asking about anything the summary does not cover (tests, CI, docs, config)
  * A terse or ambiguous reference to a filename (e.g. "SECURITY.md?")

Examples:
- "What does this project do?" → ANALYSIS_OK
- "What external dependencies does it use?" → ANALYSIS_OK
- "How is the parser subsystem structured?" → ANALYSIS_OK
- "SECURITY.md?" → NEED_DEEPER (file existence/content check)
- "Does a CONTRIBUTING.md exist?" → NEED_DEEPER (file existence check)
- "How accurate is the README?" → NEED_DEEPER (verification)
- "I think that's out of date" → NEED_DEEPER (user doubt)
- "What's in the Makefile?" → NEED_DEEPER (file content request)
- "Show me the test for X" → NEED_DEEPER (file content request)

When in doubt, respond NEED_DEEPER. It is better to run a deeper \
analysis than to give an incomplete or misleading answer."""

_SENTINEL = "NEED_DEEPER"
_CLASSIFIER_OK = "ANALYSIS_OK"


def classify_query(
    question: str,
    model: str,
    api_key: str | None,
    llm_client_factory: LLMClientFactory | None = None,
) -> tuple[bool, int, int]:
    """Classify whether a query can be answered from the codebase analysis.

    Returns ``(should_try, prompt_tokens, completion_tokens)``.  The first
    element is ``True`` if the shortcut should be attempted, ``False`` if
    the query should go straight to the full RLM engine.  Returns ``True``
    on any error or unparseable output (graceful fallback).
    """
    factory = llm_client_factory or LLMClient
    client = factory(model=model, system_prompt=_CLASSIFIER_PROMPT, api_key=api_key)

    try:
        response = client.complete([{"role": "user", "content": question}])
    except Exception:
        return (True, 0, 0)  # Graceful fallback — allow shortcut attempt

    tokens = (response.prompt_tokens, response.completion_tokens)
    # Exact match on stripped LLM output. Case-insensitive or prefix matching
    # is unnecessary — the LLM is prompted with these exact tokens, and the
    # final fallback (line below) handles any unparseable output gracefully.
    label = response.content.strip()
    if label == _SENTINEL:
        return (False, *tokens)
    if label == _CLASSIFIER_OK:
        return (True, *tokens)
    return (True, *tokens)  # Unparseable output — graceful fallback


def try_answer_from_analysis(
    question: str,
    analysis_context: str | None,
    model: str,
    api_key: str | None,
    boundary: str | None = None,
    llm_client_factory: LLMClientFactory | None = None,
) -> tuple[str, int, int] | None:
    """Try to answer a question using only the pre-computed analysis.

    Returns ``(answer, prompt_tokens, completion_tokens)`` if the LLM can
    answer from analysis alone, or ``None`` if deeper investigation is needed
    (falls through to full RLM).
    """
    if not analysis_context:
        return None

    should_try, cls_prompt, cls_completion = classify_query(
        question, model, api_key, llm_client_factory=llm_client_factory
    )
    if not should_try:
        return None

    factory = llm_client_factory or LLMClient
    client = factory(model=model, system_prompt=_SYSTEM_PROMPT, api_key=api_key)

    if boundary is not None:
        wrapped = wrap_untrusted(analysis_context, boundary)
    else:
        wrapped = f"<untrusted_document_content>\n{analysis_context}\n</untrusted_document_content>"
    user_content = f"{wrapped}\n\nQuestion: {question}"

    try:
        response = client.complete([{"role": "user", "content": user_content}])
    except Exception:
        return None  # Graceful fallback to full RLM query

    answer = response.content.strip()
    if answer == _SENTINEL:
        return None

    return (
        answer,
        cls_prompt + response.prompt_tokens,
        cls_completion + response.completion_tokens,
    )


def query_with_shortcut(
    project: Project,
    question: str,
    analysis_context: str | None,
    model: str,
    api_key: str | None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    llm_client_factory: LLMClientFactory | None = None,
) -> QueryResult | ShortcutResult:
    """Try the analysis shortcut, falling back to a full RLM query.

    Returns a ``ShortcutResult`` when the shortcut answered the question,
    or a ``QueryResult`` when the full RLM engine was used.
    """
    if analysis_context:
        boundary = generate_boundary()
        shortcut = try_answer_from_analysis(
            question,
            analysis_context,
            model,
            api_key,
            boundary=boundary,
            llm_client_factory=llm_client_factory,
        )
        if shortcut is not None:
            answer, prompt_tokens, completion_tokens = shortcut
            return ShortcutResult(
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    return project.query(question, on_progress=on_progress, cancel_event=cancel_event)
