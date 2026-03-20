# Partial Evidence Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the RLM can't answer a question, report what it found (partial evidence) and make the "More" button retry with a different search strategy.

**Architecture:** Two coordinated changes — (1) system prompt instructs LLM to report partial findings on give-up, (2) frontend `getMorePrompt()` function selects a retry prompt when the last answer starts with "I cannot answer", reverting to the default prompt after one use.

**Tech Stack:** Markdown prompts, React/TypeScript (Vitest for tests)

---

### Task 1: Update system.md Give-Up Instruction

**Files:**
- Modify: `prompts/system.md:3`

**Step 1: Edit the give-up instruction**

Replace line 3 in `prompts/system.md`. The current text is:

```
CRITICAL: You must answer ONLY using information found in the provided context documents. If the answer cannot be found in the context after thorough search, you MUST call FINAL("I cannot answer this question based on the provided documents."). You may use reasoning to synthesize, compare, and explain information from the documents, but all factual claims must be grounded in the provided context — do not introduce facts from your training data. The context is your only source of truth.
```

Replace with:

```
CRITICAL: You must answer ONLY using information found in the provided context documents. You may use reasoning to synthesize, compare, and explain information from the documents, but all factual claims must be grounded in the provided context — do not introduce facts from your training data. The context is your only source of truth.

If, after thorough search, you cannot fully answer the question, you MUST call FINAL with a message that begins with "I cannot answer this question based on the provided documents." followed by a **Partial findings** section summarizing what you DID discover (titles, dates, keywords, document regions examined) and what gaps remain. End with: "Click **More** to retry with a different search strategy."
```

**Step 2: Run prompt validator to verify system.md is still valid**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha && python -m pytest tests/unit/prompts/test_validator.py -v`
Expected: All tests PASS (system.md has no required placeholders, so content changes are safe)

**Step 3: Commit**

```
git add prompts/system.md
git commit -m "feat: instruct RLM to report partial evidence on give-up"
```

---

### Task 2: Update system_augmented.md Give-Up Instruction

**Files:**
- Modify: `prompts/system_augmented.md:3`

**Step 1: Edit the give-up instruction**

The augmented prompt currently has no explicit give-up instruction (it uses the "PRIORITIZE" framing and allows background knowledge supplementation). Add the partial-evidence instruction as a new paragraph after the background-knowledge marker block. Insert after line 9 (`Place these markers around EVERY section...`) with a blank line before and after to keep the background-knowledge section and REPL section cleanly separated:

```
If, after thorough search using both the documents and your background knowledge, you still cannot fully answer the question, you MUST call FINAL with a message that begins with "I cannot answer this question based on the provided documents." followed by a **Partial findings** section summarizing what you DID discover and what gaps remain. End with: "Click **More** to retry with a different search strategy."
```

**Step 2: Run prompt validator**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha && python -m pytest tests/unit/prompts/test_validator.py -v`
Expected: All tests PASS

**Step 3: Commit**

```
git add prompts/system_augmented.md
git commit -m "feat: add partial evidence give-up instruction to augmented prompt"
```

---

### Task 3: Write Failing Tests for getMorePrompt

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`

**Step 1: Write the failing tests**

Add a new `describe` block after the existing `'ChatArea — background knowledge hint'` block (after line 1073). Import `RETRY_SEARCH_PROMPT` and `getMorePrompt` alongside the existing imports on line 23:

Update the import on line 23 from:
```typescript
import ChatArea, { DEEPER_ANALYSIS_PROMPT } from '../ChatArea'
```
to:
```typescript
import ChatArea, { DEEPER_ANALYSIS_PROMPT, RETRY_SEARCH_PROMPT, getMorePrompt } from '../ChatArea'
```

Also add a comment to `sampleExchangeForHistory` (line 27) documenting the implicit coupling:
```typescript
/**
 * Sample exchange for tests that need non-empty history (required for More button).
 * NOTE: The `answer` value intentionally does NOT start with "I cannot answer" —
 * this matters because getMorePrompt() checks the last exchange's answer prefix
 * to decide which prompt the More button sends. Tests that use this fixture
 * implicitly test the "normal answer → DEEPER_ANALYSIS_PROMPT" path.
 */
```

Add the following test block after line 1073:

```typescript
describe('ChatArea (shared) - getMorePrompt context-sensitive selection', () => {
  it('returns DEEPER_ANALYSIS_PROMPT when exchanges is empty', () => {
    expect(getMorePrompt([])).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when last answer is a normal response', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'Here is a detailed analysis of the documents...',
    }]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns RETRY_SEARCH_PROMPT when last answer starts with "I cannot answer"', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'I cannot answer this question based on the provided documents.',
    }]
    expect(getMorePrompt(exchanges)).toBe(RETRY_SEARCH_PROMPT)
  })

  it('returns RETRY_SEARCH_PROMPT when last answer has partial evidence after "I cannot answer"', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'I cannot answer this question based on the provided documents.\n\n**Partial findings:**\n- Found 7 titles\n- Missing publication dates',
    }]
    expect(getMorePrompt(exchanges)).toBe(RETRY_SEARCH_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when only earlier exchange was a give-up but last is normal', () => {
    const exchanges = [
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-fail',
        answer: 'I cannot answer this question based on the provided documents.',
      },
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-retry',
        answer: 'After retrying, here are the titles in order...',
      },
    ]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: FAIL — `RETRY_SEARCH_PROMPT` and `getMorePrompt` are not exported from ChatArea

---

### Task 4: Implement getMorePrompt and RETRY_SEARCH_PROMPT

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx`

**Step 1: Add RETRY_SEARCH_PROMPT constant**

After the existing `DEEPER_ANALYSIS_PROMPT` constant (after line 37), add:

```typescript
/**
 * Prompt sent when the previous exchange ended in a give-up ("I cannot answer").
 * Instructs the RLM to try fundamentally different search strategies.
 */
export const RETRY_SEARCH_PROMPT =
  'The previous attempt could not answer the question. ' +
  'Try a fundamentally different exploration strategy — search for different ' +
  'keywords, examine different sections of the documents, or restructure your ' +
  'sub-LLM queries. Do not repeat the same approaches.'
```

**Step 2: Add getMorePrompt function**

After the new constant, add:

```typescript
/**
 * Select the appropriate prompt for the "More" button based on conversation context.
 *
 * When the last exchange was a give-up answer (starts with "I cannot answer"),
 * returns a retry-focused prompt. Otherwise returns the default deeper-analysis
 * prompt. After one retry, the new answer replaces the give-up as the last
 * exchange, so subsequent clicks naturally revert to the default prompt.
 */
export function getMorePrompt(exchanges: Exchange[]): string {
  const lastAnswer = exchanges[exchanges.length - 1]?.answer ?? ''
  if (lastAnswer.startsWith('I cannot answer')) {
    return RETRY_SEARCH_PROMPT
  }
  return DEEPER_ANALYSIS_PROMPT
}
```

Note: The `Exchange` type is already imported on line 7 (`import type { Exchange, WSMessage } from '../types'`).

**Step 3: Update handleMore to use getMorePrompt**

Change line 171-174 from:
```typescript
  const handleMore = useCallback(() => {
    if (!canSendMore) return
    sendQuery(DEEPER_ANALYSIS_PROMPT)
  }, [canSendMore, sendQuery])
```

to:
```typescript
  const handleMore = useCallback(() => {
    if (!canSendMore) return
    sendQuery(getMorePrompt(exchanges))
  }, [canSendMore, sendQuery, exchanges])
```

**Step 4: Run getMorePrompt tests to verify they pass**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx -t "getMorePrompt"`
Expected: All 5 getMorePrompt tests PASS

**Step 5: Commit**

```
git add src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx
git commit -m "feat: context-sensitive More button with retry prompt on give-up"
```

---

### Task 5: Update Existing Tests That Assert DEEPER_ANALYSIS_PROMPT on More Click

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`

The existing tests on lines 425-446, 472-485, and the property tests on lines 726-781 and 1079-1132 assert that clicking "More" always sends `DEEPER_ANALYSIS_PROMPT`. These still pass because `sampleExchangeForHistory` has `answer: 'Prior answer'` which does NOT start with "I cannot answer" — so `getMorePrompt` returns the default. Verify this.

**Step 1: Run the full ChatArea test suite**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: ALL tests PASS (existing tests use `sampleExchangeForHistory` with a normal answer)

**Step 2: Add a test verifying More sends RETRY_SEARCH_PROMPT after a give-up exchange**

Add inside the `'ChatArea (shared) - More button click behavior'` describe block (after the existing test on line 498):

```typescript
  it('sends RETRY_SEARCH_PROMPT when last exchange was a give-up', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    const giveUpExchange = {
      ...sampleExchangeForHistory,
      answer: 'I cannot answer this question based on the provided documents.\n\n**Partial findings:**\n- Found some titles',
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

**Step 3: Run the full ChatArea test suite again**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: ALL tests PASS

**Step 4: Commit**

```
git add src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx
git commit -m "test: add getMorePrompt unit tests and More-after-give-up integration test"
```

---

### Task 6: Run Full Test Suite

**Step 1: Run the full project test suite**

Run: `cd /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha && make all`
Expected: ALL checks pass (format, lint, typecheck, tests)

**Step 2: Fix any failures**

If any tests fail, fix them before proceeding.

---

### Task 7: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under [Unreleased]**

Under the `[Unreleased]` section, add:

```markdown
### Changed
- RLM now reports partial findings when it cannot answer a question, instead of a flat refusal
- "More" button uses a retry-focused prompt after a give-up answer, then reverts to the default deeper-analysis prompt
```

**Step 2: Commit**

```
git add CHANGELOG.md
git commit -m "docs: add changelog entry for partial evidence retry feature"
```
