# Shared HelpPanel Design

## Goal

Add a `?` help button to code-explorer and document-explorer, with
customized content for each. Refactor arxiv-explorer to use the same
shared component so all three explorers share a single HelpPanel
implementation.

## Architecture

### Shared HelpPanel component

A new `HelpPanel.tsx` in
`shared/frontend/src/components/` provides the panel shell (fixed
right-side overlay, 400px, z-40, scroll, close button, section
headings, Experimental notice) and accepts structured content props:

```ts
interface HelpPanelProps {
  onClose: () => void
  quickStart: string[]                        // ordered steps (HTML)
  faq: { q: string; a: string }[]             // Q&A pairs (HTML)
  shortcuts: { label: string; key: string }[]  // key bindings
}
```

The Experimental Notice is identical across all explorers and is baked
into the shared component.

### Shared Header change

Add an optional `onHelpToggle?: () => void` prop to the shared
`Header`. When provided, render the `?` button (question-mark-circle
SVG) before the theme toggle, using the same tooltip-btn styling as
arxiv-explorer's existing buttons.

### Per-explorer wiring

Each explorer's `App.tsx` adds `helpOpen` state and passes:
- `onHelpToggle` to the shared Header (via children or directly)
- Its own content arrays to `<HelpPanel />`

### Arxiv-explorer migration

Remove arxiv-explorer's custom `HelpPanel.tsx`. Its `Header.tsx`
wrapper continues to exist (it adds Search, Check Citations, Export
buttons), but help rendering moves to the shared component with the
existing content passed as props.

## Help Content

### Code Explorer

**Quick Start:**
1. Create a topic using the <strong>+</strong> button in the sidebar
2. Click <strong>Add Repository</strong> and paste a GitHub URL
3. Wait for the analysis to complete -- you can check status in the sidebar
4. Select repositories using the checkboxes, then ask questions in the chat
5. Click <strong>View trace</strong> on any answer to see how the LLM explored the code

**FAQ:**

| Q | A |
|---|---|
| What does the analysis status mean? | <strong>Current</strong> means the analysis reflects the latest commit. <strong>Stale</strong> means new commits exist -- click "Check for Updates" to refresh. <strong>Missing</strong> means no analysis yet -- click "Generate Analysis." |
| How do I update a repository's analysis? | Open the repository detail view and click "Check for Updates." If new commits are found, the analysis is regenerated automatically. |
| Can a repository belong to multiple topics? | Yes. Use the context menu on a repository to add it to additional topics. |
| What does the context budget indicator mean? | It estimates how much of the model's context window is used by your repositories and conversation. Green (<50%), amber (<80%), red (>=80%). |
| Why do queries take so long? | Shesha uses a recursive approach: the LLM writes code to explore your repositories, runs it, examines the output, and repeats. This takes multiple iterations. |

**Shortcuts:** Enter (send), Shift+Enter (newline), Escape (cancel).

### Document Explorer

**Quick Start:**
1. Create a topic using the <strong>+</strong> button in the sidebar
2. Click <strong>Upload</strong> and drag-and-drop or select files
3. Organize documents into topics using the context menu
4. Select documents using the checkboxes, then ask questions in the chat
5. Click <strong>View trace</strong> on any answer to see how the LLM explored your documents

**FAQ:**

| Q | A |
|---|---|
| What file types can I upload? | PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), RTF, and any plain-text file -- including Markdown, CSV, HTML, config files, and source code. |
| What are the "Sources" shown below answers? | They list which documents the LLM consulted to produce the answer. Click a source tag to view that document's details. |
| Can a document belong to multiple topics? | Yes. Open the document detail view to see which topics it belongs to and add or remove it from others. |
| What does the context budget indicator mean? | It estimates how much of the model's context window is used by your documents and conversation. Green (<50%), amber (<80%), red (>=80%). |
| Why do queries take so long? | Shesha uses a recursive approach: the LLM writes code to explore your documents, runs it, examines the output, and repeats. This takes multiple iterations. |

**Shortcuts:** Enter (send), Shift+Enter (newline), Escape (cancel).

### Arxiv Explorer (unchanged content, migrated to shared props)

**Quick Start:**
1. Create a topic using the <strong>+</strong> button in the sidebar
2. Click the <strong>Search</strong> icon to find papers on arXiv
3. Select papers and click <strong>Add</strong> to add them to your topic
4. Ask questions about your papers in the chat area
5. Click <strong>View trace</strong> on any answer to see how the LLM arrived at it

**FAQ:** Existing 6 pairs unchanged (topics, context budget, query speed,
cancel, citation check, export).

**Shortcuts:** Enter (send), Shift+Enter (newline), Escape (cancel).

## Files Changed

| File | Change |
|------|--------|
| `shared/frontend/src/components/HelpPanel.tsx` | **New** -- shared panel component |
| `shared/frontend/src/components/HelpPanel.test.tsx` | **New** -- tests |
| `shared/frontend/src/components/Header.tsx` | Add optional `onHelpToggle` prop + `?` button |
| `shared/frontend/src/components/__tests__/Header.test.tsx` | Test help button rendering |
| `shared/frontend/src/index.ts` | Export HelpPanel |
| `code_explorer/frontend/src/App.tsx` | Add helpOpen state, pass content to HelpPanel |
| `document_explorer/frontend/src/App.tsx` | Add helpOpen state, pass content to HelpPanel |
| `web/frontend/src/App.tsx` | Use shared HelpPanel, remove local HelpPanel import |
| `web/frontend/src/components/HelpPanel.tsx` | **Delete** |
| `web/frontend/src/components/Header.tsx` | Remove help button (now in shared Header) |
| `web/frontend/src/components/__tests__/Header.test.tsx` | Update tests |
