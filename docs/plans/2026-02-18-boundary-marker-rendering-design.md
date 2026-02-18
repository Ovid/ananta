# Boundary Marker Rendering Design

## Problem

The RLM wraps document content in boundary markers (`UNTRUSTED_CONTENT_{hex}_BEGIN` / `_END`) for prompt injection defense. When the LLM quotes document content verbatim in its answer, these markers leak into the user-facing text. Users see raw tokens like `UNTRUSTED_CONTENT_bd0e753b7146bd0089d21bfab2c51ded_BEGIN` with no context for what they mean.

## Goal

Replace boundary markers with a visually distinct highlighted blockquote so users can see that enclosed text is quoted document content.

## Approach

Pre-process the answer text in the frontend before passing it to react-markdown. No backend changes — raw answer text stays intact in storage and traces.

## Design

### Utility function

**File:** `shared/frontend/src/utils/sanitize.ts`

A function `stripBoundaryMarkers(text: string): string` that:

1. Matches boundary marker pairs via regex:
   `UNTRUSTED_CONTENT_[0-9a-f]{32}_BEGIN\n?(content)\n?UNTRUSTED_CONTENT_[0-9a-f]{32}_END`
2. Extracts the inner content from each match.
3. Prefixes every line with `> ` (blank lines get just `>`).
4. Prepends a label line: `> **Quoted content**\n>\n`.
5. Returns the transformed text.

### Integration

In `ChatMessage.tsx`, call the utility before passing to `<Markdown>`:

```tsx
<Markdown components={mdComponents}>{stripBoundaryMarkers(exchange.answer)}</Markdown>
```

Export from shared-ui `index.ts` so the web app's custom `renderAnswer` can also apply it before citation parsing.

### Styling

No changes to blockquote styling. The existing style (`border-l-2 border-accent pl-3 my-2 text-text-dim italic`) is kept. The `**Quoted content**` label distinguishes these from regular blockquotes.

### Decisions

- **Transform layer:** Frontend only. Backend stays untouched.
- **Display style:** Highlighted blockquote (always visible, no collapse).
- **Label:** Generic "Quoted content" — we cannot reliably distinguish subcall vs code output vs document content from the markers alone.
- **Blockquote styling:** Keep existing italic style; the label provides sufficient distinction.
