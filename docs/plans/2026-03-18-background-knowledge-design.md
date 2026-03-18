# Background Knowledge Toggle — Design

## Problem

Shesha's system prompt restricts the LLM to document-only knowledge to reduce
hallucinations. This works well for factual grounding but creates a hard ceiling:
when documents don't cover a topic, the LLM cannot fill gaps — even when the user
explicitly wants it to. The "More" button hits this same wall, telling users it
can't expand because it's limited to document content.

## Solution

A sidebar checkbox ("Allow background knowledge") that switches the system prompt
to one that lets the LLM supplement document content with its training knowledge,
while clearly separating the two in the output.

## Design

### 1. Prompt Architecture

Two system prompts:

- **`prompts/system.md`** (existing, unchanged) — strict document-only mode.
- **`prompts/system_augmented.md`** (new) — replaces the "CRITICAL" paragraph with
  instructions to:
  - Prioritize document content as the primary source of truth.
  - Supplement with background knowledge when documents are insufficient.
  - Clearly separate the two: document-grounded content first, then inferred
    content wrapped in `<!-- BACKGROUND_KNOWLEDGE_START -->` /
    `<!-- BACKGROUND_KNOWLEDGE_END -->` HTML comment markers.

The markers let the frontend detect and style augmented sections without being
visible in raw Markdown.

### 2. Frontend — Sidebar Checkbox

- Location: **TopicSidebar**, below the topics list.
- Label: **"Allow background knowledge"**
- Default: **unchecked** (strict document-only mode).
- State owned by each explorer's `App.tsx`, passed down as a prop (same pattern
  as `selectedDocuments`).
- TopicSidebar gains a new optional prop: `bottomControls?: ReactNode` — a slot
  for rendering controls below the topic list. This keeps the shared component
  generic.
- The checkbox state is passed to `ChatArea`, which includes
  `allow_background_knowledge` in the WebSocket query message.

### 3. Frontend — Augmented Content Rendering

When a response contains `<!-- BACKGROUND_KNOWLEDGE_START -->` /
`<!-- BACKGROUND_KNOWLEDGE_END -->` markers, the renderer splits the answer into
segments:

- **Document-grounded segments** — rendered normally, as today.
- **Background knowledge segments** — wrapped in a styled block:
  - Subtle warm tint background (light: amber-50ish, dark: muted warm tone).
  - Left border accent (~3px, amber/warm color).
  - Text label at top: **"Background knowledge"** in small, muted font.
  - `<aside role="complementary" aria-label="Background knowledge">` for screen
    readers.
  - Contrast ratios verified for both themes (WCAG AA, 4.5:1 minimum).

Parsing logic lives in a utility function `splitAugmentedSections(answer: string)`
used by `ChatMessage.tsx`. If no markers are present, rendering is unchanged —
zero impact on existing behavior.

### 4. Backend — WebSocket & RLM Integration

**WebSocket message** — the `query` message gains one field:

```json
{
  "type": "query",
  "topic": "...",
  "question": "...",
  "document_ids": ["..."],
  "allow_background_knowledge": false
}
```

**`shared/websockets.py`** — reads `allow_background_knowledge` from the message,
passes it to the RLM engine.

**`rlm/engine.py`** — query method accepts optional `allow_background_knowledge`
parameter. When true, `PromptLoader` loads `system_augmented.md` instead of
`system.md`.

**`prompts/loader.py`** — `render_system_prompt()` accepts a parameter to select
the prompt file. Security boundary token logic applies identically to both
prompts.

Change path: one new field flows frontend → WebSocket → engine → prompt loader.
No changes to sandbox, tracing, or container infrastructure.

### 5. "More" Button Behavior

The "More" button respects the checkbox state — if "Allow background knowledge"
is checked, "More" sends `allow_background_knowledge: true` with its deeper
analysis prompt.

If the checkbox is off and the LLM's "More" response indicates it can't expand
further (document ceiling), the UI appends a hint nudging the user to enable
background knowledge.

### 6. Help Panel Updates

Two new FAQ entries added to all three explorers:

**"More" button:**
> **Q:** What does the "More" button do?
> **A:** It asks the AI to verify and expand its previous analysis. It checks for
> completeness, accuracy, and relevance, then presents an updated report with any
> changes highlighted. Requires at least one prior exchange.

**"Allow background knowledge":**
> **Q:** What does "Allow background knowledge" do?
> **A:** By default, answers are based strictly on your documents — this reduces
> hallucinations but may leave gaps where documents don't cover a topic. When
> enabled, the AI supplements document content with its general knowledge.
> Background knowledge sections are visually marked with a warm-tinted block so
> you can always tell what came from your documents versus the AI's training data.

## Accessibility

- Color is never the sole differentiator — text label is the primary signal.
- `<aside role="complementary" aria-label="Background knowledge">` for screen
  readers.
- Left border accent provides a third visual channel for color-blind users.
- Contrast ratios meet WCAG AA (4.5:1) in both light and dark themes.
