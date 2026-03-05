# UX Fixes: Auto-Growing Input, Markdown User Messages, Per-Topic Chat

**Date:** 2026-03-05
**Branch:** ovid/ux-fixes

## Problem

Three UX issues in the shared web tools:

1. **Input area is single-line.** The textarea has `rows={1}` and `resize-none` -- long
   prompts become invisible. Should grow as users type, up to ~4 lines.

2. **User messages render as plain text.** Assistant answers get full markdown (headers,
   code blocks, lists) but user questions are raw `<p>` tags -- long input appears as a
   wall of text.

3. **Code explorer chat is global, not per-topic.** ArXiv explorer already scopes history
   to the active topic. Code explorer uses a single global `conversation.json`, so
   switching topics shows the same chat.

## Design

### 1. Auto-Growing Textarea (shared ChatArea.tsx)

Add a `useEffect` on the textarea ref that fires on every `input` change:

- Reset `style.height = 'auto'` to collapse to content height
- Set `style.height = Math.min(el.scrollHeight, maxHeight)` where `maxHeight = 6rem`
- Beyond 4 lines, internal scroll activates via `overflow-y: auto`
- Keep `rows={1}` as the minimum
- Remove `resize-none` (controlled resize replaces it)

No new dependencies. Standard ref + effect pattern.

### 2. Markdown User Messages (shared ChatMessage.tsx)

Replace the plain `<p>` rendering of user questions with the same `<Markdown>` renderer
used for assistant answers:

```tsx
// Before
<p className="...">{exchange.question}</p>

// After
<Markdown components={mdComponents}>{exchange.question}</Markdown>
```

- Reuse existing `mdComponents` (headers, code, lists, blockquotes)
- Do NOT apply `stripBoundaryMarkers()` -- those markers only appear in assistant output
- The outer wrapper (right-aligned, accent background) stays unchanged

### 3. Per-Topic Chat History (code explorer only)

**Backend:**

- `api.py`: Replace `_get_global_session()` with `_get_topic_session()` that resolves
  the topic name to `topics/{topic_name}/conversation.json` via the topic manager
- `websockets.py`: Save exchanges to the topic-specific session instead of `state.session`.
  The topic name is already present in the WebSocket `query` message payload.
- Old global `conversation.json` left in place but unused. No migration (fresh start).

**Frontend:**

- `App.tsx`: Change `loadHistory` callback to pass the topic name through instead of
  ignoring it (`_topic` -> `topic`)
- `api.ts`: Remove the custom global history endpoint; use the shared per-topic endpoint
  (`/api/topics/{name}/history`) which the shared router already provides

**Shared layer: No changes needed.** The shared `ChatArea`, `useAppState`, and `routes.py`
already support per-topic history. This is purely a code explorer wiring fix.

## Files Touched

| Layer | Files |
|-------|-------|
| Shared frontend | `ChatArea.tsx`, `ChatMessage.tsx` |
| Code explorer frontend | `App.tsx`, `api.ts` |
| Code explorer backend | `api.py`, `websockets.py` |
| Tests | New tests for each change |
| Docs | `extending-web-tools.md` (update if outdated) |

## What Stays Untouched

- ArXiv explorer (already works correctly for all three issues)
- Shared backend routes
- Shared hooks (`useAppState`, `useWebSocket`)

## Testing

| Change | Test |
|--------|------|
| Auto-grow textarea | Vitest: verify height adjusts with content, caps at max |
| User message markdown | Vitest: render ChatMessage with markdown question, assert elements |
| Per-topic history (backend) | pytest: different sessions for different topics |
| Per-topic history (WS) | pytest: exchange saved to topic session, not global |
