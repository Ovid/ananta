# Structured `PARTIAL()` Callable for Give-Up Detection

**Date:** 2026-03-20
**Supersedes:** String-prefix detection in `2026-03-20-partial-evidence-retry-design.md`

## Problem

The current implementation detects give-up answers by checking
`answer.startsWith('I cannot answer')` in the frontend. This is fragile because:

- The LLM may rephrase (e.g., "Unfortunately, I cannot answer...")
- The LLM may add markdown formatting (e.g., `**I cannot answer**`)
- The detection logic is coupled to prose that the LLM controls

Moving the `startsWith` check to the backend doesn't fix the fundamental issue: we're
parsing free-form LLM output to infer structured state.

## Solution: `PARTIAL()` callable

Add a new callable `PARTIAL(...)` alongside the existing `FINAL(...)` and
`FINAL_VAR(...)`. The RLM calls `PARTIAL(...)` instead of `FINAL(...)` when it
found partial evidence but could not fully answer the question.

### Three RLM outcomes

| Outcome | Callable | `gave_up` flag | "More" prompt |
|---------|----------|----------------|---------------|
| Full answer | `FINAL(...)` | `false` | `DEEPER_ANALYSIS_PROMPT` |
| No answer at all | `FINAL("I cannot answer...")` | `false` | `DEEPER_ANALYSIS_PROMPT` |
| Partial evidence found | `PARTIAL(...)` | `true` | `RETRY_SEARCH_PROMPT` |

Only the partial-evidence case triggers the retry prompt. A flat "no answer" does
not, because there's no evidence trail suggesting a retry would help.

### Detection is unambiguous

The parser already distinguishes `FINAL` from `FINAL_VAR` by returning a type tag.
Adding `PARTIAL` is the same pattern: `find_final_answer()` returns
`("partial", content)` and the engine sets `QueryResult.gave_up = True`. No string
matching on the answer text anywhere.

## Changes by layer

### 1. System prompts (`prompts/system.md`, `prompts/system_augmented.md`)

Replace the current "I cannot answer" instruction (line 5) with the following.
The same change applies to `system_augmented.md` (adapted for its framing).

Additionally, update the existing `FINAL()` format documentation block (lines 78-106
in `system.md`) to mention `PARTIAL`:
- Rename the heading from "FINAL() FORMAT — CRITICAL:" to
  "FINAL() and PARTIAL() FORMAT — CRITICAL:"
- Add `PARTIAL` to the REPL builtins list (item 4 or similar): "A `PARTIAL` function
  that works like `FINAL` but signals partial evidence — see instructions above."
- No need to duplicate the full format rules — the "same format rules as FINAL" note
  in the `PARTIAL` instruction is sufficient, but seeing `PARTIAL` in the format
  heading reinforces that it exists.

> If, after thorough search, you found some relevant evidence but cannot fully
> answer the question, use PARTIAL instead of FINAL. PARTIAL follows the same
> format rules as FINAL — raw Markdown, no surrounding quotes, real line breaks.
>
> PARTIAL(## Partial Findings
>
> I found evidence related to the question but could not fully answer it.
>
> **What I found:**
> - Titles, dates, keywords, or document regions examined
>
> **What is missing:**
> - Gaps that remain
>
> Click **More** to retry with a different search strategy.)
>
> Use PARTIAL OR FINAL, never both. If you found nothing relevant at all, use
> FINAL("I cannot answer this question based on the provided documents.") as
> before — PARTIAL is only for cases where you found partial evidence.

### 2. Sandbox (`src/shesha/sandbox/runner.py`, `base.py`)

The LLM can call `FINAL(...)` inside `\`\`\`repl` code blocks, where it executes as
a real Python function. `PARTIAL` must be registered the same way, or the sandbox
raises `NameError`.

- `runner.py`: Add `PartialAnswer` class (mirrors `FinalAnswer`), `make_partial()`
  factory, register `PARTIAL` in `BUILTINS_SET` and `register_builtins()`.
- `runner.py`: In the result-detection block (`isinstance(rv, FinalAnswer)`), add a
  branch for `PartialAnswer` that sets `result["partial_answer"] = rv.answer`.
- `base.py`: Add `partial_answer: str | None = None` to `ExecutionResult`.
- `executor.py`: Map `result.get("partial_answer")` into `ExecutionResult`.

### 3. Parser (`src/shesha/rlm/engine.py`: `find_final_answer`)

Extend the regex to match bare-text `PARTIAL(...)`. Return `("partial", content)` as
the type tag. `PARTIAL_VAR` is not supported — `PARTIAL` always contains inline text.

**Important:** The existing `_is_python_identifier` heuristic (which converts
`FINAL(some_var)` → `("final_var", "some_var")`) must NOT apply to `PARTIAL`. The
`PARTIAL` regex path must skip that heuristic entirely and always return
`("partial", content)` with the content treated as literal text. Otherwise
`PARTIAL(findings)` would be misrouted as a variable reference that nobody handles.

The `PARTIAL` path must still call `_strip_string_quotes()` on the captured content.
The LLM may write `PARTIAL("some text\nmore text")` with quotes out of habit, and
without stripping, the user would see literal `\"` and `\n` in the partial findings.

### 4. RLM engine (`src/shesha/rlm/engine.py`)

- Add `gave_up: bool = False` to `QueryResult` dataclass.
- **Bare-text path:** At every code path that processes a `find_final_answer` result,
  if the type tag is `"partial"`, set `gave_up=True` on the `QueryResult`.
- **Sandbox path:** In `_execute_code_blocks`, detect `result.partial_answer` (from
  the sandbox `PartialAnswer` class) the same way `result.final_answer` is detected,
  and propagate `gave_up=True`.
- The answer text from `PARTIAL(...)` is stored in `QueryResult.answer` as-is (it
  contains the partial findings narrative).

### 5. Backend schemas & WebSocket (`src/shesha/experimental/shared/`)

- `schemas.py`: Add `gave_up: bool = False` to `ExchangeSchema`.
- `session.py`: `add_exchange()` accepts and stores `gave_up`.
- `websockets.py`: `build_complete_response()` includes `gave_up` field. Both
  `_handle_query` and `handle_multi_project_query` pass `result.gave_up` through.

### 6. Frontend types (`types/index.ts`)

Add `gave_up?: boolean` to the `Exchange` interface and to the `complete` variant
of `WSMessage`.

### 7. Frontend logic (`ChatArea.tsx`)

`getMorePrompt()` changes from:

```typescript
if (lastAnswer.startsWith('I cannot answer')) {
```

to:

```typescript
if (exchanges[exchanges.length - 1]?.gave_up) {
```

No string matching. The self-reverting behavior is preserved: after a retry produces
a normal answer (with `gave_up: false`), subsequent "More" clicks use the default
prompt.

## What NOT to change

- `FINAL()` and `FINAL_VAR()` behavior remains identical.
- Trace format is unchanged (the step type is still `FINAL_ANSWER`; the metadata
  `source` field records `"bare_partial"` or similar).

## Testing

### Sandbox tests
- `PARTIAL("text")` in a `\`\`\`repl` block produces `ExecutionResult.partial_answer`
- `PARTIAL` is listed in `BUILTINS_SET` and registered in namespace
- `PartialAnswer` sets `_return_value_` and is detected in result dict

### Parser tests
- Bare-text `PARTIAL(some text)` returns `("partial", "some text")`
- `PARTIAL` inside a code block is ignored (same as `FINAL`)
- `PARTIAL_VAR(x)` is NOT supported (keep it simple)

### Engine tests
- When RLM returns `PARTIAL(...)` via bare text, `QueryResult.gave_up` is `True`
- When RLM returns `PARTIAL(...)` via sandbox, `QueryResult.gave_up` is `True`
- When RLM returns `FINAL(...)`, `QueryResult.gave_up` is `False`
- Answer text from `PARTIAL(...)` is stored verbatim in `QueryResult.answer`

### Backend tests
- `ExchangeSchema` serializes `gave_up` field
- `build_complete_response` includes `gave_up`
- History endpoint returns `gave_up` in exchange data

### Frontend tests
- `getMorePrompt` checks `gave_up` field instead of answer text
- Existing tests updated to use `gave_up` flag
- More button sends `RETRY_SEARCH_PROMPT` when `gave_up: true`
- More button sends `DEEPER_ANALYSIS_PROMPT` when `gave_up: false`
