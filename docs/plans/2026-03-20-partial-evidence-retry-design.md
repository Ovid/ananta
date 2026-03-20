# Partial Evidence Reporting & Context-Sensitive "More" Button

**Date:** 2026-03-20
**Origin:** Investigation of failed Barsoom title search trace vs. successful retry

## Problem

When the RLM cannot answer a question, it returns a flat "I cannot answer this
question based on the provided documents." This discards all partial evidence the
RLM found during its search (e.g., titles extracted, dates found, document regions
examined). The user has no signal about whether retrying might help.

The "More" button always sends the same `DEEPER_ANALYSIS_PROMPT`, which assumes a
substantive report exists. After a give-up answer, the "More" prompt is
inappropriate.

## Solution

Two coordinated changes:

### 1. System prompt: report partial evidence on give-up

Modify the give-up instruction in `prompts/system.md` (and `system_augmented.md`)
so the RLM reports what it DID find before giving up. The answer still starts with
"I cannot answer this question based on the provided documents." but continues
with a **Partial findings** section and a hint to click **More**.

### 2. Frontend: context-sensitive "More" prompt

Make the "More" button select its prompt based on the last exchange:

- If the last answer starts with "I cannot answer" -> use a retry-focused prompt
  that instructs the RLM to try fundamentally different search strategies
- Otherwise -> use the existing `DEEPER_ANALYSIS_PROMPT`

The one-shot revert is automatic: after the retry produces a real answer, the last
exchange no longer starts with "I cannot answer", so the next "More" click uses
the default prompt. Clearing the chat empties `exchanges`, also reverting to
default.

## Files Changed

1. `prompts/system.md` — reword line 3 give-up instruction
2. `prompts/system_augmented.md` — same change adapted for "PRIORITIZE" framing
3. `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx` — add
   `RETRY_SEARCH_PROMPT`, `getMorePrompt()`, update `handleMore`

## What NOT to Change

- No backend changes
- No new component state (derived from existing `exchanges` array)
- No changes to the `Exchange` type or WebSocket protocol

## Detection Logic

```typescript
function getMorePrompt(exchanges: Exchange[]): string {
  const lastAnswer = exchanges[exchanges.length - 1]?.answer ?? ''
  if (lastAnswer.startsWith('I cannot answer')) {
    return RETRY_SEARCH_PROMPT
  }
  return DEEPER_ANALYSIS_PROMPT
}
```

Future context-sensitive prompts add conditions before the default return.

## Testing

- `getMorePrompt()` — unit test as pure function:
  - Empty exchanges -> default prompt
  - Last answer starts with "I cannot answer" -> retry prompt
  - Last answer starts with "I cannot answer" + partial evidence -> retry prompt
  - Last answer is a normal response -> default prompt
- Prompt validator tests — existing tests verify modified `.md` files pass validation
- Manual verification — re-run Barsoom title search to confirm partial evidence in output
