# OOLONG Base-Mode Structured Output Design

## Problem

The OOLONG benchmark script (`oolong/run_oolong_and_pairs.py`) uses brittle regex
parsing to extract answers from base-model (single-shot LiteLLM) responses. Three
functions are affected:

| Function | Lines | Brittleness |
|----------|-------|-------------|
| `_extract_candidate()` | 192-200 | Strips "Answer:", "Label:" prefixes from last line; misses variations like "The answer is..." |
| `score_oolong()` list parse | 208-216 | `ast.literal_eval` on bracket-delimited text; fails on malformed brackets or JSON arrays |
| `parse_pairs_from_text()` | 256-267 | Extracts `(int, int)` pairs via `\d+` regex per line; picks up stray numbers from prose |

These parse **model output** and are genuinely brittle. A fourth regex
(`_parse_labeled_context()`) parses the dataset itself and is stable.

## Scope

- **Base mode only.** The RLM path (`call_rlm()` / `project.query()`) is not
  changed. Other code depends on the RLM output format as-is.
- **Both benchmarks.** OOLONG (single-answer QA) and OOLONG-Pairs (pair-finding).

## Approach

Use LiteLLM's `response_format={"type": "json_object"}` parameter to request JSON
output from the model, and parse it with `json.loads()` instead of regex. Fall back
to the existing regex extraction with a logged warning if JSON parsing fails.

### Why this approach

- `response_format={"type": "json_object"}` is broadly supported (OpenAI,
  Anthropic, Gemini via LiteLLM).
- No schema definition needed at the API level; just convention plus `json.loads()`.
- The regex fallback handles older models or malformed responses gracefully.
- Stricter alternatives (`json_schema` mode) are OpenAI-only and add complexity
  without meaningful benefit given the fallback.

## Design

### 1. Changes to `call_base()`

`call_base()` (line 587) gains a `benchmark` parameter and passes
`response_format` to the LiteLLM `completion()` call:

```python
_OOLONG_JSON_SUFFIX = '\n\nRespond with JSON only: {"answer": "<your answer>"}'
_PAIRS_JSON_SUFFIX = (
    "\n\nRespond with JSON only: "
    '{"pairs": [[id1, id2], ...]} where each pair has the smaller ID first.'
)

def call_base(prompt: str, model: str, benchmark: str) -> tuple[str, int]:
    suffix = _OOLONG_JSON_SUFFIX if benchmark == "oolong" else _PAIRS_JSON_SUFFIX
    resp = completion(
        model=model,
        messages=[{"role": "user", "content": prompt + suffix}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    tokens = resp.get("usage", {}).get("total_tokens", 0) or 0
    return resp["choices"][0]["message"]["content"], tokens
```

`call_base()` is only called from two places inside `run_oolong_and_pairs.py`
(lines 883 and 949). No external code imports it.

### 2. Prompt suffixes

A JSON instruction is appended to the prompt depending on benchmark type:

- **OOLONG:** `Respond with JSON only: {"answer": "<your answer>"}`
- **OOLONG-Pairs:** `Respond with JSON only: {"pairs": [[id1, id2], ...]} where each pair has the smaller ID first.`

These suffixes are short and do not meaningfully affect token count. The RLM path
prompts are not touched.

### 3. New JSON parsing helpers

Two new private functions:

**`_parse_oolong_json(raw: str) -> str | None`**
- Calls `json.loads(raw)`
- Returns `parsed["answer"]` if the key exists and value is a string
- Returns `None` on any failure (invalid JSON, missing key, wrong type)

**`_parse_pairs_json(raw: str) -> set[tuple[int, int]] | None`**
- Calls `json.loads(raw)`
- Looks for `parsed["pairs"]` as a list of 2-element lists
- Normalizes each pair to `(min, max)` order, filters self-pairs
- Returns `None` on any failure

### 4. Call site changes

**OOLONG (~line 883):**
```python
pred, toks = call_base(prompt, model, benchmark="oolong")
answer = _parse_oolong_json(pred)
if answer is None:
    log.warning("JSON parse failed for base oolong id=%s, falling back to regex", row["id"])
    answer = pred  # existing score_oolong handles raw text via regex
s = score_oolong(answer, row["answer"])
```

**OOLONG-Pairs (~line 949):**
```python
pred, toks = call_base(prompt, model, benchmark="pairs")
pred_pairs = _parse_pairs_json(pred)
if pred_pairs is None:
    log.warning("JSON parse failed for base pairs t=%d, falling back to regex", t_idx)
    pred_pairs = parse_pairs_from_text(pred)
s = f1_score(pred_pairs, gold_pairs)
```

### 5. Fallback and warning behavior

When JSON parsing fails:
- A warning is logged via the existing `log` logger (goes to both `last-run.log`
  and stderr)
- The existing regex parsing runs as before
- No data points are lost

### 6. What does NOT change

| Component | Why unchanged |
|-----------|---------------|
| `score_oolong()` | Scoring logic stays the same; receives cleaner input from JSON path |
| `parse_pairs_from_text()` | Kept as regex fallback; external consumers import it |
| `f1_score()` | Pure scoring function, input-agnostic |
| `_extract_candidate()` | Still used by `score_oolong()` in the fallback path |
| `call_rlm()` | RLM path is out of scope |
| `_parse_labeled_context()` | Parses dataset format, not model output |
| `run_reference_implementation.py` imports | Only imports scoring functions and utilities, not `call_base` |
| `tests/unit/test_oolong_scoring.py` | Only imports `score_oolong` |

### 7. New tests

New unit tests for the JSON parsing helpers:

- `_parse_oolong_json()`: valid JSON, missing key, wrong type, invalid JSON, empty string
- `_parse_pairs_json()`: valid pairs, self-pair filtering, min/max normalization, missing key, invalid JSON, empty string

Existing `score_oolong` tests remain unchanged.

## Files Changed

| File | Change |
|------|--------|
| `oolong/run_oolong_and_pairs.py` | `call_base()` gains `benchmark` param + `response_format`; two new JSON helpers; two call sites updated with JSON-first + fallback |
| `tests/unit/test_oolong_scoring.py` | New tests for `_parse_oolong_json()` and `_parse_pairs_json()` |
