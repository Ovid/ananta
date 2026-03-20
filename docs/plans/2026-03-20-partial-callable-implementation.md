# PARTIAL() Callable Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fragile `startsWith('I cannot answer')` detection with a structured `PARTIAL()` callable that unambiguously signals partial evidence from the RLM.

**Architecture:** Add `PARTIAL(...)` alongside `FINAL(...)` / `FINAL_VAR(...)` at every layer: sandbox runtime, bare-text parser, RLM engine, backend schemas/WebSocket, and frontend. A `gave_up` boolean flag propagates from `QueryResult` through to the frontend `Exchange`, replacing string matching.

**Tech Stack:** Python (sandbox runner, RLM engine, Pydantic schemas), TypeScript/React (ChatArea, types), Vitest (frontend tests), pytest (backend tests)

---

### Task 1: Sandbox — Register `PARTIAL` in the Docker sandbox runner

The LLM can call `PARTIAL(...)` inside ````repl` code blocks, where it runs as Python. Without registration, this raises `NameError`.

**Files:**
- Modify: `src/shesha/sandbox/runner.py:44-55` (BUILTINS_SET)
- Modify: `src/shesha/sandbox/runner.py:140-193` (classes, factories, register_builtins)
- Modify: `src/shesha/sandbox/runner.py:207-218` (result detection block)
- Modify: `src/shesha/sandbox/base.py:8-20` (ExecutionResult)
- Modify: `src/shesha/sandbox/executor.py:234-244` (ExecutionResult mapping)
- Test: `tests/unit/sandbox/test_runner.py`

**Step 1: Write failing tests**

Add these tests to `tests/unit/sandbox/test_runner.py`:

```python
from shesha.sandbox.runner import BUILTINS_SET


def test_partial_in_builtins_set():
    """PARTIAL and PartialAnswer must be in BUILTINS_SET so SHOW_VARS excludes them."""
    assert "PARTIAL" in BUILTINS_SET
    assert "PartialAnswer" in BUILTINS_SET


class TestPartialAnswer:
    """Tests for PARTIAL() callable in the sandbox protocol."""

    def test_partial_produces_partial_answer_in_result(self) -> None:
        """PARTIAL('text') in sandbox sets result['partial_answer']."""
        import sys

        from shesha.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "PARTIAL('Found 7 titles but no dates')",
                    }
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        result = messages[0]
        assert result["partial_answer"] == "Found 7 titles but no dates"
        # return_value should be cleared (not JSON serializable)
        assert result["return_value"] is None

    def test_partial_callable_after_reset(self) -> None:
        """PARTIAL remains callable after namespace reset."""
        import sys

        from shesha.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message({"action": "reset"}),
                frame_message({"action": "execute", "code": "print(callable(PARTIAL))"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        # msg 0: reset result
        # msg 1: execute result
        assert messages[1]["status"] == "ok"
        assert messages[1]["stdout"] == "True\n"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/sandbox/test_runner.py::test_partial_in_builtins_set tests/unit/sandbox/test_runner.py::TestPartialAnswer -v`
Expected: FAIL — `"PARTIAL" not in BUILTINS_SET`, `NameError: name 'PARTIAL' is not defined`

**Step 3: Implement sandbox changes**

In `src/shesha/sandbox/runner.py`:

1. Add `"PARTIAL"` and `"PartialAnswer"` to `BUILTINS_SET` (line 44-55):

```python
BUILTINS_SET: frozenset[str] = frozenset(
    [
        "llm_query",
        "llm_query_batched",
        "FINAL",
        "FINAL_VAR",
        "PARTIAL",
        "FinalAnswer",
        "FinalVar",
        "PartialAnswer",
        "SHOW_VARS",
        "context",
    ]
)
```

2. Add `PartialAnswer` class after `FinalVar` (inside `main()`, after line 147):

```python
    class PartialAnswer:
        def __init__(self, answer: str):
            self.answer = answer
```

3. Add `make_partial` factory after `make_final_var` (after line 181):

```python
    def make_partial(answer: str) -> PartialAnswer:
        """Create PartialAnswer and register it for detection."""
        pa = PartialAnswer(answer)
        NAMESPACE["_return_value_"] = pa
        return pa
```

4. Register in `register_builtins()` (after line 188):

```python
        NAMESPACE["PARTIAL"] = make_partial
        NAMESPACE["PartialAnswer"] = PartialAnswer
```

5. Add detection branch in the result processing block (after line 218, the `elif isinstance(rv, FinalVar):` block):

```python
                elif isinstance(rv, PartialAnswer):
                    result["partial_answer"] = rv.answer
                    result["return_value"] = None  # Not JSON serializable
```

In `src/shesha/sandbox/base.py`, add to `ExecutionResult` (after line 19):

```python
    partial_answer: str | None = None
```

In `src/shesha/sandbox/executor.py`, add to the `ExecutionResult` constructor (after line 242):

```python
                    partial_answer=result.get("partial_answer"),
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/sandbox/test_runner.py::test_partial_in_builtins_set -v`
Expected: PASS

**Step 5: Run full sandbox tests**

Run: `pytest tests/unit/sandbox/ -v`
Expected: All pass — no existing behavior changed.

**Step 6: Commit**

```
git add src/shesha/sandbox/runner.py src/shesha/sandbox/base.py src/shesha/sandbox/executor.py tests/unit/sandbox/test_runner.py
git commit -m "feat: register PARTIAL() callable in sandbox runtime"
```

---

### Task 2: Parser — Extend `find_final_answer` to match bare-text `PARTIAL(...)`

**Files:**
- Modify: `src/shesha/rlm/engine.py:97-187` (find_final_answer)
- Test: `tests/unit/rlm/test_engine.py` (TestFindFinalAnswer class, ~line 2506)

**Step 1: Write failing tests**

Add these tests to the `TestFindFinalAnswer` class in `tests/unit/rlm/test_engine.py`:

```python
    def test_find_final_answer_bare_partial(self):
        """Detects bare PARTIAL(text) outside code blocks."""
        result = find_final_answer("PARTIAL(Found 7 titles but no dates)")
        assert result == ("partial", "Found 7 titles but no dates")

    def test_find_final_answer_partial_strips_quotes(self):
        """PARTIAL('quoted text') strips surrounding quotes."""
        result = find_final_answer("PARTIAL(\"Some partial findings\")")
        assert result == ("partial", "Some partial findings")

    def test_find_final_answer_partial_ignores_inside_repl_block(self):
        """Does NOT match PARTIAL inside a ```repl block (handled by executor)."""
        text = '```repl\nPARTIAL("partial findings")\n```'
        result = find_final_answer(text)
        assert result is None

    def test_find_final_answer_partial_identifier_stays_literal(self):
        """PARTIAL(findings) with a bare identifier is treated as literal text,
        NOT as a variable reference. Unlike FINAL, PARTIAL has no VAR variant."""
        result = find_final_answer("PARTIAL(findings)")
        assert result == ("partial", "findings")

    def test_find_final_answer_partial_multiline(self):
        """PARTIAL with multiline content is captured."""
        text = "PARTIAL(## Partial Findings\n\nFound some titles\n\n**Missing:** dates)"
        result = find_final_answer(text)
        assert result is not None
        assert result[0] == "partial"
        assert "Found some titles" in result[1]
        assert "Missing" in result[1]

    def test_find_final_answer_partial_with_leading_whitespace(self):
        """PARTIAL at start of line with whitespace is detected."""
        result = find_final_answer("  PARTIAL(partial text)")
        assert result == ("partial", "partial text")

    def test_find_final_answer_partial_not_mid_line(self):
        """PARTIAL mid-line (not at start) should NOT match."""
        result = find_final_answer("The result is PARTIAL(text)")
        assert result is None

    def test_find_final_answer_partial_empty_returns_none(self):
        """Bare PARTIAL( with no content should return None."""
        result = find_final_answer("PARTIAL(")
        assert result is None

    def test_find_final_answer_partial_takes_priority_over_final(self):
        """When both PARTIAL and FINAL appear, PARTIAL should match first
        (since it appears before FINAL in the text)."""
        text = "PARTIAL(partial text)\nFINAL(full answer)"
        result = find_final_answer(text)
        assert result == ("partial", "partial text")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_engine.py -k "partial" -v`
Expected: All FAIL — `find_final_answer` doesn't recognize `PARTIAL`

**Step 3: Implement parser changes**

In `src/shesha/rlm/engine.py`, modify `find_final_answer()`. Add PARTIAL detection
**before** the FINAL_VAR check (so PARTIAL takes priority). Insert after the code-block
stripping (line 131) and before the FINAL_VAR check (line 133):

```python
    # Check PARTIAL first — it has no VAR variant and no identifier heuristic.
    # The content is always treated as literal text.
    partial_pattern = r"^\s*PARTIAL\((.*)\)\s*\Z"
    partial_match = re.search(partial_pattern, stripped, re.MULTILINE | re.DOTALL)
    if partial_match:
        partial_content = partial_match.group(1).strip()
        if partial_content:
            return ("partial", _strip_string_quotes(partial_content))
    else:
        # Pass 1b for PARTIAL: single line
        partial_line = re.search(r"^\s*PARTIAL\((.*)\)\s*$", stripped, re.MULTILINE)
        if partial_line:
            partial_content = partial_line.group(1).strip()
            if partial_content:
                return ("partial", _strip_string_quotes(partial_content))
        else:
            # Pass 2 for PARTIAL: no closing paren
            partial_anchor = re.search(r"^\s*PARTIAL\(", stripped, re.MULTILINE)
            if partial_anchor:
                partial_content = stripped[partial_anchor.end():].strip()
                if partial_content:
                    return ("partial", _strip_string_quotes(partial_content))
```

Also update the docstring to document the new return type:

```
    Returns:
        ("final", answer_string) for FINAL(...) with literal content
        ("final_var", variable_name) for FINAL_VAR(...) or FINAL(identifier)
        ("partial", answer_string) for PARTIAL(...) with literal content
        None if no pattern found
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_engine.py -k "partial" -v`
Expected: All PASS

**Step 5: Run full find_final_answer tests**

Run: `pytest tests/unit/rlm/test_engine.py -k "TestFindFinalAnswer" -v`
Expected: All existing tests still pass — no FINAL behavior changed.

**Step 6: Commit**

```
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: extend find_final_answer to detect bare-text PARTIAL()"
```

---

### Task 3: Engine — Add `gave_up` to `QueryResult` and propagate through both code paths

**Files:**
- Modify: `src/shesha/rlm/engine.py:49-57` (QueryResult dataclass)
- Modify: `src/shesha/rlm/engine.py:190-197` (_CodeBlockResult dataclass)
- Modify: `src/shesha/rlm/engine.py:494-627` (_execute_code_blocks method)
- Modify: `src/shesha/rlm/engine.py:912-960` (bare-text FINAL/PARTIAL handling in query loop)
- Modify: `src/shesha/rlm/engine.py:982-1050` (post-code-block FINAL/PARTIAL handling)
- Test: `tests/unit/rlm/test_engine.py`

**Step 1: Write failing tests**

Add to `tests/unit/rlm/test_engine.py`, in the `TestRLMEngine` class:

```python
    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_false_for_final(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is False when RLM returns FINAL(...)."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='FINAL(The answer is 42)',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True

        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is False

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_true_for_bare_partial(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is True when RLM returns bare PARTIAL(...)."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='PARTIAL(Found 7 titles but no dates)',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True

        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is True
        assert result.answer == "Found 7 titles but no dates"

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_true_for_sandbox_partial(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is True when sandbox returns partial_answer."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nPARTIAL("Found some evidence")\n```',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True
        mock_executor.execute.return_value = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
            partial_answer="Found some evidence",
        )

        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is True
        assert result.answer == "Found some evidence"
```

Note: The test file will need `ExecutionResult` imported. Check if it's already imported; if not, add it to the imports at the top.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_engine.py -k "gave_up" -v`
Expected: FAIL — `QueryResult` has no `gave_up` attribute

**Step 3: Implement engine changes**

1. Add `gave_up` to `QueryResult` (after line 57):

```python
    gave_up: bool = False
```

2. Add `gave_up` to `_CodeBlockResult` (after line 197):

```python
    gave_up: bool = False
```

3. In `_execute_code_blocks` (line 494-627), add detection of `result.partial_answer` after the `result.final_answer` check (after line 567 `break`). The new branch goes between the `final_answer` check and the `final_var` check:

```python
            elif result.partial_answer is not None:
                final_answer = (
                    result.partial_answer
                    if isinstance(result.partial_answer, str)
                    else str(result.partial_answer)
                )
                gave_up = True
                step = trace.add_step(
                    type=StepType.FINAL_ANSWER,
                    content=final_answer,
                    iteration=iteration,
                    metadata={"source": "code_block_partial"},
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.FINAL_ANSWER,
                        iteration,
                        final_answer,
                        copy.copy(token_usage),
                    )
                break
```

Also initialize `gave_up = False` at the top of `_execute_code_blocks` (next to `final_answer = None`), and include it in the return:

```python
        return _CodeBlockResult(
            final_answer=final_answer,
            all_output=all_output,
            exec_results=exec_results,
            failed_final_var=failed_final_var,
            gave_up=gave_up,
        )
```

4. In the main `query()` loop, handle bare-text `PARTIAL`. Where bare `FINAL` is processed (around line 912-960), add a check: if `bare_final` type is `"partial"`, set `gave_up=True` on the `QueryResult`:

For the bare-text path with no code blocks (line 916 `if bare_final is not None:`), after resolving the answer, construct QueryResult with `gave_up`:

```python
                    query_result = QueryResult(
                        answer=bare_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                        gave_up=(final_type == "partial"),
                    )
```

For the post-code-block bare_final path (around line 1003 `if final_answer is not None:`), similarly set `gave_up` based on whether the type was `"partial"`:

The metadata source should be `"bare_partial"` or `"bare_partial_after_code"` when the type is partial.

5. Where `cb_result.final_answer` is used to build the final `QueryResult` (around line 1041-1050):

```python
                    query_result = QueryResult(
                        answer=final_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=execution_time,
                        verification=verification,
                        semantic_verification=semantic_verification,
                        gave_up=cb_result.gave_up,
                    )
```

**Key implementation detail:** The `"partial"` type from `find_final_answer` should NOT go through the `_is_python_identifier` / `_resolve_final_var` path. In the bare-text handling, when `final_type == "partial"`, always treat `final_value` as literal text (it already is, because `find_final_answer` skips the identifier heuristic for `PARTIAL`).

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_engine.py -k "gave_up" -v`
Expected: All PASS

**Step 5: Run full engine tests**

Run: `pytest tests/unit/rlm/test_engine.py -v`
Expected: All existing tests still pass.

**Step 6: Commit**

```
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: propagate gave_up flag through QueryResult for PARTIAL()"
```

---

### Task 4: Backend schemas — Add `gave_up` to ExchangeSchema, session, and WebSocket

**Files:**
- Modify: `src/shesha/experimental/shared/schemas.py:62-72` (ExchangeSchema)
- Modify: `src/shesha/experimental/shared/session.py:46-72` (add_exchange)
- Modify: `src/shesha/experimental/shared/websockets.py:36-63` (build_complete_response)
- Modify: `src/shesha/experimental/shared/websockets.py:328-353` (_handle_query call sites)
- Modify: `src/shesha/experimental/shared/websockets.py:534-559` (handle_multi_project_query call sites)
- Test: `tests/unit/experimental/shared/test_schemas.py`
- Test: `tests/unit/experimental/web/test_session.py`
- Test: `tests/unit/experimental/shared/test_ws.py`

**Step 1: Write failing tests**

In `tests/unit/experimental/shared/test_schemas.py`:

```python
def test_exchange_schema_gave_up_default():
    """gave_up defaults to False when not provided."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    assert e.gave_up is False


def test_exchange_schema_gave_up_true():
    """gave_up=True is stored and serialized."""
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="Partial findings here.",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
        gave_up=True,
    )
    assert e.gave_up is True
    d = e.model_dump()
    assert d["gave_up"] is True
```

In `tests/unit/experimental/web/test_session.py`:

```python
def test_add_exchange_stores_gave_up(session: WebConversationSession) -> None:
    """add_exchange stores gave_up flag when provided."""
    exchange = session.add_exchange(
        question="What?",
        answer="Partial evidence.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
        gave_up=True,
    )
    assert exchange["gave_up"] is True

    # Verify persistence
    reloaded = WebConversationSession(session._file.parent)
    assert reloaded.list_exchanges()[0]["gave_up"] is True


def test_add_exchange_gave_up_defaults_to_false(session: WebConversationSession) -> None:
    """gave_up defaults to False when not provided."""
    exchange = session.add_exchange(
        question="What?",
        answer="Full answer.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert exchange["gave_up"] is False
```

In `tests/unit/experimental/shared/test_ws.py`, add to `TestBuildCompleteResponse`:

```python
    def test_includes_gave_up_field(self) -> None:
        """Response includes gave_up field."""
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
        resp = build_complete_response(
            answer="Partial findings.",
            trace_id="t-001",
            token_usage=usage,
            execution_time=1.5,
            document_ids=["doc-a"],
            document_bytes=512,
            allow_background_knowledge=False,
            gave_up=True,
        )
        assert resp["gave_up"] is True

    def test_gave_up_defaults_to_false(self) -> None:
        """gave_up defaults to False when not provided."""
        usage = TokenUsage()
        resp = build_complete_response(
            answer="Full answer.",
            trace_id=None,
            token_usage=usage,
            execution_time=0.5,
            document_ids=[],
            document_bytes=0,
            allow_background_knowledge=False,
        )
        assert resp["gave_up"] is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/shared/test_schemas.py -k "gave_up" tests/unit/experimental/web/test_session.py -k "gave_up" tests/unit/experimental/shared/test_ws.py -k "gave_up" -v`
Expected: All FAIL

**Step 3: Implement backend changes**

1. In `src/shesha/experimental/shared/schemas.py`, add to `ExchangeSchema` (after line 72):

```python
    gave_up: bool = False
```

2. In `src/shesha/experimental/shared/session.py`, add `gave_up` parameter to `add_exchange()`:

After `allow_background_knowledge: bool = False,` add:
```python
        gave_up: bool = False,
```

In the exchange dict construction, add:
```python
            "gave_up": gave_up,
```

3. In `src/shesha/experimental/shared/websockets.py`:

Add `gave_up: bool = False` parameter to `build_complete_response()`:
```python
def build_complete_response(
    *,
    answer: str,
    trace_id: str | None,
    token_usage: TokenUsage,
    execution_time: float,
    document_ids: list[str],
    document_bytes: int,
    allow_background_knowledge: bool,
    gave_up: bool = False,
) -> dict[str, object]:
```

Add to the return dict:
```python
        "gave_up": gave_up,
```

4. Update both call sites in `websockets.py`:

In `_handle_query` (around line 328-353), add to `session.add_exchange()`:
```python
        gave_up=result.gave_up,
```

And to `build_complete_response()`:
```python
            gave_up=result.gave_up,
```

In `handle_multi_project_query` (around line 534-559), same two additions:
```python
        gave_up=result.gave_up,
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/shared/test_schemas.py -k "gave_up" tests/unit/experimental/web/test_session.py -k "gave_up" tests/unit/experimental/shared/test_ws.py -k "gave_up" -v`
Expected: All PASS

**Step 5: Run full backend test suites**

Run: `pytest tests/unit/experimental/shared/ tests/unit/experimental/web/test_session.py -v`
Expected: All existing tests still pass. The `test_builds_expected_fields` test in `test_ws.py` will fail because the expected dict doesn't include `gave_up`. Update it to include `"gave_up": True` → actually `"gave_up": False` since `allow_background_knowledge=True` but `gave_up` is not passed so defaults to `False`. Add `"gave_up": False` to the expected dict in that test.

**Step 6: Commit**

```
git add src/shesha/experimental/shared/schemas.py src/shesha/experimental/shared/session.py src/shesha/experimental/shared/websockets.py tests/unit/experimental/shared/test_schemas.py tests/unit/experimental/web/test_session.py tests/unit/experimental/shared/test_ws.py
git commit -m "feat: add gave_up field to ExchangeSchema, session, and WebSocket response"
```

---

### Task 5: Frontend types — Add `gave_up` to Exchange and WSMessage

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/types/index.ts:45-56` (Exchange)
- Modify: `src/shesha/experimental/shared/frontend/src/types/index.ts:73-78` (WSMessage)

**Step 1: Add `gave_up` to the Exchange interface**

In `src/shesha/experimental/shared/frontend/src/types/index.ts`:

Add after `allow_background_knowledge?: boolean` (line 55):
```typescript
  gave_up?: boolean
```

Add `gave_up?: boolean` to the `complete` variant of `WSMessage` (line 76):
```typescript
  | { type: 'complete'; answer: string; trace_id: string | null; tokens: { prompt: number; completion: number; total: number }; duration_ms: number; document_ids?: string[]; document_bytes?: number; gave_up?: boolean }
```

**Step 2: Verify TypeScript compiles**

Run from the shared frontend directory:
```bash
cd src/shesha/experimental/shared/frontend && npx tsc --noEmit
```
Expected: No errors.

**Step 3: Commit**

```
git add src/shesha/experimental/shared/frontend/src/types/index.ts
git commit -m "feat: add gave_up field to Exchange and WSMessage types"
```

---

### Task 6: Frontend logic — Switch `getMorePrompt` to use `gave_up` flag

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx:57-63` (getMorePrompt)
- Test: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`

**Step 1: Update tests to use `gave_up` flag**

In `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`:

Update `getMorePrompt` unit tests to use the `gave_up` field. Replace the existing `describe('ChatArea (shared) - getMorePrompt context-sensitive selection')` block:

```typescript
describe('ChatArea (shared) - getMorePrompt context-sensitive selection', () => {
  it('returns DEEPER_ANALYSIS_PROMPT when exchanges is empty', () => {
    expect(getMorePrompt([])).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when last exchange has no gave_up flag', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'Here is a detailed analysis of the documents...',
    }]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when last exchange has gave_up=false', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      gave_up: false,
    }]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns RETRY_SEARCH_PROMPT when last exchange has gave_up=true', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'Found some titles but not enough to answer.',
      gave_up: true,
    }]
    expect(getMorePrompt(exchanges)).toBe(RETRY_SEARCH_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when only earlier exchange had gave_up but last is normal', () => {
    const exchanges = [
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-fail',
        gave_up: true,
      },
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-retry',
        answer: 'After retrying, here are the titles in order...',
        gave_up: false,
      },
    ]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })
})
```

Also update the integration test `sends RETRY_SEARCH_PROMPT when last exchange was a give-up`:

```typescript
  it('sends RETRY_SEARCH_PROMPT when last exchange was a give-up', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    const giveUpExchange = {
      ...sampleExchangeForHistory,
      answer: 'Found some evidence but not enough.',
      gave_up: true,
    }
    await renderChatArea({
      wsSend,
      loadHistory: vi.fn().mockResolvedValue([giveUpExchange]),
    })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        question: RETRY_SEARCH_PROMPT,
      })
    )
  })
```

**Step 2: Run tests to verify they fail**

Run from the shared frontend directory:
```bash
cd src/shesha/experimental/shared/frontend && npx vitest run --reporter=verbose src/components/__tests__/ChatArea.test.tsx
```
Expected: The updated tests fail because `getMorePrompt` still checks `startsWith`.

**Step 3: Update `getMorePrompt` implementation**

In `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx`, replace the `getMorePrompt` function (lines 57-63):

```typescript
export function getMorePrompt(exchanges: Exchange[]): string {
  if (exchanges[exchanges.length - 1]?.gave_up) {
    return RETRY_SEARCH_PROMPT
  }
  return DEEPER_ANALYSIS_PROMPT
}
```

Update the JSDoc to reflect the new detection method:

```typescript
/**
 * Select the appropriate prompt for the "More" button based on conversation context.
 *
 * When the last exchange has the gave_up flag set (indicating the RLM called
 * PARTIAL instead of FINAL), returns a retry-focused prompt. Otherwise returns
 * the default deeper-analysis prompt. After one retry, the new exchange has
 * gave_up=false, so subsequent clicks naturally revert to the default prompt.
 */
```

**Step 4: Run tests to verify they pass**

Run:
```bash
cd src/shesha/experimental/shared/frontend && npx vitest run --reporter=verbose src/components/__tests__/ChatArea.test.tsx
```
Expected: All PASS

**Step 5: Run full frontend test suite**

Run:
```bash
cd src/shesha/experimental/shared/frontend && npx vitest run --reporter=verbose
```
Expected: All pass.

**Step 6: Commit**

```
git add src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx
git commit -m "feat: switch getMorePrompt to use gave_up flag instead of string matching"
```

---

### Task 7: System prompts — Replace give-up instruction with `PARTIAL()` documentation

**Files:**
- Modify: `prompts/system.md`
- Modify: `prompts/system_augmented.md`

**Step 1: Update `prompts/system.md`**

1. Replace line 5 (the "I cannot answer" instruction) with:

```
If, after thorough search, you found some relevant evidence but cannot fully answer the question, use PARTIAL instead of FINAL. PARTIAL follows the same format rules as FINAL — raw Markdown, no surrounding quotes, real line breaks.

PARTIAL(## Partial Findings

I found evidence related to the question but could not fully answer it.

**What I found:**
- Titles, dates, keywords, or document regions examined

**What is missing:**
- Gaps that remain

Click **More** to retry with a different search strategy.)

Use PARTIAL OR FINAL, never both. If you found nothing relevant at all, use FINAL("I cannot answer this question based on the provided documents.") as before — PARTIAL is only for cases where you found partial evidence.
```

2. Add `PARTIAL` to the REPL builtins list (after item 4, line 11). Add as item 5:

```
5. A `PARTIAL` function that works like `FINAL` but signals you found partial evidence — see instructions above.
```

Renumber the existing item 5 ("The ability to use `print()` statements…") to item 6.

3. Update the format heading (line 82):

From: `FINAL() FORMAT — CRITICAL:`
To: `FINAL() and PARTIAL() FORMAT — CRITICAL:`

4. Update the "two options" block (line 78-80) to mention PARTIAL:

```
IMPORTANT: When you are done with the iterative process, you MUST provide a final answer. You have three options:
1. Use FINAL(your final answer here) to provide the answer directly
2. Use FINAL_VAR(variable_name) to return a string variable you have created in the REPL
3. Use PARTIAL(your partial findings here) when you found evidence but cannot fully answer — this signals a retry may help
```

**Step 2: Update `prompts/system_augmented.md`**

Apply the same changes, adapted for the augmented framing:

1. Replace line 11 (the "I cannot answer" instruction for augmented mode):

```
If, after thorough search using both the documents and your background knowledge, you still cannot fully answer the question but found some relevant evidence, use PARTIAL instead of FINAL. PARTIAL follows the same format rules as FINAL — raw Markdown, no surrounding quotes, real line breaks. Include what you DID discover and what gaps remain, ending with: "Click **More** to retry with a different search strategy." If you found nothing relevant at all, use FINAL("I cannot answer this question based on the provided documents.").
```

2. Add `PARTIAL` to the REPL builtins list (same as system.md — item 5).

3. Update the format heading and options block (same as system.md).

**Step 3: Verify prompt validation tests pass**

Run: `pytest tests/ -k "prompt" -v`
Expected: Any existing prompt validation tests still pass.

**Step 4: Commit**

```
git add prompts/system.md prompts/system_augmented.md
git commit -m "feat: document PARTIAL() callable in system prompts"
```

---

### Task 8: Changelog — Document the change

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Under `## [Unreleased]`, update the existing "Changed" entries. Replace the current entries about partial evidence:

```markdown
### Changed

- RLM uses structured `PARTIAL()` callable instead of string-prefix detection for partial evidence answers
- "More" button detects partial evidence via `gave_up` flag instead of parsing answer text
```

**Step 2: Commit**

```
git add CHANGELOG.md
git commit -m "docs: update changelog for PARTIAL() callable"
```

---

### Task 9: Verify — Full test suite

**Step 1: Run all Python tests**

Run: `make all`
Expected: Format, lint, typecheck, and all tests pass.

**Step 2: Run all frontend tests**

Run:
```bash
cd src/shesha/experimental/shared/frontend && npx vitest run --reporter=verbose
```
Expected: All pass.

**Step 3: Run TypeScript compilation for all frontends**

Check that other frontends that import from `@shesha/shared-ui` still compile:
```bash
cd src/shesha/experimental/web/frontend && npx tsc --noEmit
cd src/shesha/experimental/code_explorer/frontend && npx tsc --noEmit
cd src/shesha/experimental/document_explorer/frontend && npx tsc --noEmit
```
Expected: All pass — `gave_up` is optional so existing code doesn't break.
