# "Documents Only" Notice — Design

## Problem

When "Allow background knowledge" is checked but the LLM's response doesn't use
any background knowledge (documents fully covered the answer), there's no
indication of this. The user can't tell whether background knowledge was used or
not.

## Solution

When a response was made with background knowledge allowed but contains no
background knowledge markers, show a subtle muted notice at the bottom of the
answer: *"Based entirely on your documents — no background knowledge was needed."*

## Design

### 1. Visibility Rules

The notice appears **only** when:
- The exchange was made with `allow_background_knowledge: true`
- The response contains no `<!-- BACKGROUND_KNOWLEDGE_START -->` markers

It does NOT appear when:
- The checkbox was off when the query was made
- The response contains background knowledge sections (the tinted blocks are
  sufficient indication)

### 2. Backend — Store flag per exchange

**WebSocket `complete` message** — include `allow_background_knowledge` in the
response payload so the frontend knows the flag's value for this specific query.

**Session storage** — `session.add_exchange()` saves `allow_background_knowledge`
alongside existing fields (`tokens`, `model`, `document_ids`). Old exchanges
without this field default to `false` when loaded from history.

Both `_handle_query` and `handle_multi_project_query` in `websockets.py` already
have the `allow_background` variable — they just need to include it in the
`complete` message and `add_exchange()` call.

### 3. Frontend — Exchange type

The `Exchange` TypeScript type gains:
```typescript
allow_background_knowledge?: boolean
```

Optional so old history entries (without the field) default to `undefined`/falsy.

### 4. Frontend — ChatMessage rendering

In `ChatMessage.tsx`, in the default rendering path (after `splitAugmentedSections`):

- If `hasBackground` is false AND `exchange.allow_background_knowledge` is true,
  render a muted notice after the Markdown content:

```typescript
{!hasBackground && exchange.allow_background_knowledge && (
  <p className="text-[10px] text-text-dim mt-2 italic">
    Based entirely on your documents — no background knowledge was needed.
  </p>
)}
```

### 5. Style

- `text-[10px]` — same size as token count metadata
- `text-text-dim` — muted color, doesn't draw attention
- `italic` — distinguishes it from answer content
- No background tint, no border — this is the quiet/expected case
