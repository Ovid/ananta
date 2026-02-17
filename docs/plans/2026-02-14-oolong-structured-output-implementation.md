# OOLONG Structured Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace brittle regex parsing of base-mode LLM responses in the OOLONG benchmark script with JSON structured output via LiteLLM's `response_format`, falling back to existing regex with a warning.

**Architecture:** Add `response_format={"type": "json_object"}` to the base-mode LiteLLM call, append JSON format instructions to prompts, and parse responses with `json.loads()`. Two new private helpers extract answers from JSON. Existing scoring functions are untouched.

**Tech Stack:** Python, LiteLLM (`response_format`), `json` stdlib

**Design doc:** `docs/plans/2026-02-14-oolong-structured-output-design.md`

---

### Task 1: Add `_parse_oolong_json()` with tests

**Files:**
- Modify: `tests/unit/test_oolong_scoring.py`
- Modify: `oolong/run_oolong_and_pairs.py:~175` (new function before scoring section)

**Step 1: Write the failing tests**

Add to `tests/unit/test_oolong_scoring.py`. Update the import at line 11 to also import `_parse_oolong_json`:

```python
from oolong.run_oolong_and_pairs import score_oolong, _parse_oolong_json
```

Then add a new test class after the existing ones:

```python
# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


class TestParseOolongJson:
    def test_valid_json(self):
        assert _parse_oolong_json('{"answer": "entity"}') == "entity"

    def test_missing_key(self):
        assert _parse_oolong_json('{"response": "entity"}') is None

    def test_answer_not_string(self):
        """Numeric answer values should be coerced to string."""
        assert _parse_oolong_json('{"answer": 42}') == "42"

    def test_invalid_json(self):
        assert _parse_oolong_json("not json at all") is None

    def test_empty_string(self):
        assert _parse_oolong_json("") is None

    def test_answer_with_whitespace(self):
        assert _parse_oolong_json('{"answer": "  human being  "}') == "human being"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_oolong_scoring.py::TestParseOolongJson -v`
Expected: FAIL — `ImportError: cannot import name '_parse_oolong_json'`

**Step 3: Write minimal implementation**

Add `import json` to the imports at the top of `oolong/run_oolong_and_pairs.py` (after line 88, with the other stdlib imports). Then add this function before the `# Scoring: OOLONG` comment block (before line 172):

```python
def _parse_oolong_json(raw: str) -> str | None:
    """Try to extract answer from JSON response. Returns None on failure."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or "answer" not in parsed:
        return None
    answer = parsed["answer"]
    if not isinstance(answer, str):
        answer = str(answer)
    return _normalize_ws(answer)
```

Note: `_normalize_ws` is defined at line 177 — the new function must go **after** it. Place it between `_normalize_ws` (line 178) and `_parse_gold_answers` (line 181). Or, place it after `_normalize_ws` and before the `_parse_gold_answers` function.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_oolong_scoring.py::TestParseOolongJson -v`
Expected: all 6 tests PASS

**Step 5: Commit**

```bash
git add tests/unit/test_oolong_scoring.py oolong/run_oolong_and_pairs.py
git commit -m "feat(oolong): add _parse_oolong_json helper with tests"
```

---

### Task 2: Add `_parse_pairs_json()` with tests

**Files:**
- Modify: `tests/unit/test_oolong_scoring.py`
- Modify: `oolong/run_oolong_and_pairs.py` (new function near `_parse_oolong_json`)

**Step 1: Write the failing tests**

Update the import in `tests/unit/test_oolong_scoring.py`:

```python
from oolong.run_oolong_and_pairs import score_oolong, _parse_oolong_json, _parse_pairs_json
```

Add a new test class:

```python
class TestParsePairsJson:
    def test_valid_pairs(self):
        raw = '{"pairs": [[1, 3], [2, 5]]}'
        assert _parse_pairs_json(raw) == {(1, 3), (2, 5)}

    def test_normalizes_order(self):
        """Pairs should be (min, max) regardless of input order."""
        raw = '{"pairs": [[5, 2], [3, 1]]}'
        assert _parse_pairs_json(raw) == {(2, 5), (1, 3)}

    def test_filters_self_pairs(self):
        raw = '{"pairs": [[1, 1], [2, 3]]}'
        assert _parse_pairs_json(raw) == {(2, 3)}

    def test_missing_key(self):
        assert _parse_pairs_json('{"results": [[1, 2]]}') is None

    def test_invalid_json(self):
        assert _parse_pairs_json("User 1 and User 3") is None

    def test_empty_string(self):
        assert _parse_pairs_json("") is None

    def test_empty_pairs_list(self):
        assert _parse_pairs_json('{"pairs": []}') == set()

    def test_non_two_element_sublists_skipped(self):
        """Sublists that aren't exactly 2 elements are skipped."""
        raw = '{"pairs": [[1, 2, 3], [4, 5]]}'
        assert _parse_pairs_json(raw) == {(4, 5)}
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_oolong_scoring.py::TestParsePairsJson -v`
Expected: FAIL — `ImportError: cannot import name '_parse_pairs_json'`

**Step 3: Write minimal implementation**

Add right after `_parse_oolong_json` in `oolong/run_oolong_and_pairs.py`:

```python
def _parse_pairs_json(raw: str) -> set[tuple[int, int]] | None:
    """Try to extract pairs from JSON response. Returns None on failure."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or "pairs" not in parsed:
        return None
    raw_pairs = parsed["pairs"]
    if not isinstance(raw_pairs, list):
        return None
    pairs: set[tuple[int, int]] = set()
    for item in raw_pairs:
        if not isinstance(item, list) or len(item) != 2:
            continue
        try:
            a, b = int(item[0]), int(item[1])
        except (ValueError, TypeError):
            continue
        if a == b:
            continue
        lo, hi = (a, b) if a < b else (b, a)
        pairs.add((lo, hi))
    return pairs
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_oolong_scoring.py::TestParsePairsJson -v`
Expected: all 8 tests PASS

**Step 5: Commit**

```bash
git add tests/unit/test_oolong_scoring.py oolong/run_oolong_and_pairs.py
git commit -m "feat(oolong): add _parse_pairs_json helper with tests"
```

---

### Task 3: Update `call_base()` to use `response_format`

**Files:**
- Modify: `oolong/run_oolong_and_pairs.py:587-595`

**Step 1: Write the failing test**

This function calls LiteLLM externally so we test it indirectly via integration. No new unit test needed — the change is mechanical. We verify correctness by running all existing tests to check nothing breaks.

Run: `pytest tests/unit/test_oolong_scoring.py -v`
Expected: all existing tests PASS (baseline)

**Step 2: Modify `call_base()`**

Replace the function at lines 587-595 with:

```python
_OOLONG_JSON_SUFFIX = '\n\nRespond with JSON only: {"answer": "<your answer>"}'
_PAIRS_JSON_SUFFIX = (
    "\n\nRespond with JSON only: "
    '{"pairs": [[id1, id2], ...]} where each pair has the smaller ID first.'
)


def call_base(prompt: str, model: str, benchmark: str) -> tuple[str, int]:
    """Run a single-shot base model call. Returns (answer_string, total_tokens_used).

    Args:
        prompt: The full prompt (context + question).
        model: LiteLLM model identifier.
        benchmark: Either "oolong" or "pairs" — determines JSON format instruction.
    """
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

**Step 3: Run tests to verify nothing broke**

Run: `pytest tests/unit/test_oolong_scoring.py -v`
Expected: all tests PASS (same as baseline — no test calls `call_base` directly)

**Step 4: Commit**

```bash
git add oolong/run_oolong_and_pairs.py
git commit -m "feat(oolong): add response_format and benchmark param to call_base"
```

---

### Task 4: Wire up JSON parsing at the OOLONG call site

**Files:**
- Modify: `oolong/run_oolong_and_pairs.py:880-904`

**Step 1: No new unit test needed**

The call site is deep inside `main()` and requires LLM + dataset access to run. The JSON parsing helpers are already tested in Tasks 1-2. This is a wiring change.

**Step 2: Update the OOLONG base call site**

Replace lines 883-884:

```python
                            pred, toks = call_base(prompt, model)
                            s = score_oolong(pred, row["answer"])
```

With:

```python
                            pred, toks = call_base(prompt, model, benchmark="oolong")
                            answer = _parse_oolong_json(pred)
                            if answer is None:
                                log.warning(
                                    "JSON parse failed for base oolong id=%s, "
                                    "falling back to regex",
                                    row["id"],
                                )
                                answer = pred
                            s = score_oolong(answer, row["answer"])
```

**Step 3: Run tests to verify nothing broke**

Run: `pytest tests/unit/test_oolong_scoring.py -v`
Expected: all tests PASS

**Step 4: Run linting**

Run: `ruff check oolong/run_oolong_and_pairs.py`
Expected: no errors

**Step 5: Commit**

```bash
git add oolong/run_oolong_and_pairs.py
git commit -m "feat(oolong): wire JSON parsing at OOLONG base call site"
```

---

### Task 5: Wire up JSON parsing at the OOLONG-Pairs call site

**Files:**
- Modify: `oolong/run_oolong_and_pairs.py:949-950`

**Step 1: No new unit test needed**

Same rationale as Task 4 — the parsing helpers are tested, this is wiring.

**Step 2: Update the pairs base call site**

Replace lines 949-950:

```python
                            pred, toks = call_base(prompt, model)
                            pred_pairs = parse_pairs_from_text(pred)
```

With:

```python
                            pred, toks = call_base(prompt, model, benchmark="pairs")
                            pred_pairs = _parse_pairs_json(pred)
                            if pred_pairs is None:
                                log.warning(
                                    "JSON parse failed for base pairs t=%d, "
                                    "falling back to regex",
                                    t_idx,
                                )
                                pred_pairs = parse_pairs_from_text(pred)
```

**Step 3: Run tests to verify nothing broke**

Run: `pytest tests/unit/test_oolong_scoring.py -v`
Expected: all tests PASS

**Step 4: Run full quality checks**

Run: `ruff check oolong/ && ruff format --check oolong/ && mypy oolong/run_oolong_and_pairs.py`
Expected: clean on all three

**Step 5: Commit**

```bash
git add oolong/run_oolong_and_pairs.py
git commit -m "feat(oolong): wire JSON parsing at OOLONG-Pairs base call site"
```

---

### Task 6: Final verification

**Files:** None (read-only verification)

**Step 1: Run full test suite**

Run: `pytest tests/unit/test_oolong_scoring.py -v`
Expected: all tests PASS, including both new test classes

**Step 2: Run linting and formatting**

Run: `ruff check oolong/ tests/unit/test_oolong_scoring.py && ruff format --check oolong/ tests/unit/test_oolong_scoring.py`
Expected: clean

**Step 3: Run mypy**

Run: `mypy oolong/run_oolong_and_pairs.py`
Expected: clean (or only pre-existing issues unrelated to this change)

**Step 4: Verify imports in dependent files still work**

Run: `python -c "from oolong.run_oolong_and_pairs import score_oolong, f1_score, parse_pairs_from_text, make_pairs_tasks, plot_results, CTX_LENS, CACHE_PATH, _human_len, _parse_labeled_context, _build_user_stats; print('OK')"`
Expected: prints `OK` — confirms `run_reference_implementation.py` imports are unbroken

**Step 5: Review the diff**

Run: `git diff main -- oolong/ tests/unit/test_oolong_scoring.py`
Verify: only expected changes, no accidental modifications to scoring functions or RLM path
