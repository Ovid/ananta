# Shared HelpPanel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `?` help button to all three explorers with customized content, using a single shared HelpPanel component.

**Architecture:** Create a shared `HelpPanel` component that accepts structured props (quickStart, faq, shortcuts). Add an optional `onHelpToggle` prop to the shared `Header` to render the `?` button. Migrate arxiv-explorer off its custom HelpPanel. Wire help into code-explorer and document-explorer.

**Tech Stack:** React, TypeScript, Vitest, @testing-library/react

---

### Task 1: Shared HelpPanel Component — Tests

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/__tests__/HelpPanel.test.tsx`

**Step 1: Write the failing tests**

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import HelpPanel from '../HelpPanel'

const defaultProps = {
  onClose: vi.fn(),
  quickStart: [
    'Step one',
    'Step <strong>two</strong>',
  ],
  faq: [
    { q: 'Question one?', a: 'Answer one.' },
    { q: 'Question two?', a: 'Answer <strong>two</strong>.' },
  ],
  shortcuts: [
    { label: 'Send message', key: 'Enter' },
    { label: 'New line', key: 'Shift+Enter' },
  ],
}

describe('HelpPanel', () => {
  it('renders the Help heading', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Help')).toBeInTheDocument()
  })

  it('renders quick start steps as an ordered list', () => {
    render(<HelpPanel {...defaultProps} />)
    const items = screen.getAllByRole('listitem')
    // Ordered list items for quick start
    expect(items[0]).toHaveTextContent('Step one')
    expect(items[1]).toHaveTextContent('Step two')
  })

  it('renders HTML in quick start steps', () => {
    render(<HelpPanel {...defaultProps} />)
    const items = screen.getAllByRole('listitem')
    const strong = within(items[1]).getByText('two')
    expect(strong.tagName).toBe('STRONG')
  })

  it('renders FAQ questions and answers', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Question one?')).toBeInTheDocument()
    expect(screen.getByText('Answer one.')).toBeInTheDocument()
    expect(screen.getByText('Question two?')).toBeInTheDocument()
  })

  it('renders HTML in FAQ answers', () => {
    render(<HelpPanel {...defaultProps} />)
    const strong = screen.getByText('two')
    expect(strong.tagName).toBe('STRONG')
  })

  it('renders keyboard shortcuts', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Send message')).toBeInTheDocument()
    expect(screen.getByText('Enter')).toBeInTheDocument()
    expect(screen.getByText('New line')).toBeInTheDocument()
    expect(screen.getByText('Shift+Enter')).toBeInTheDocument()
  })

  it('renders the experimental notice', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText(/experimental software/i)).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(<HelpPanel {...defaultProps} onClose={onClose} />)
    await userEvent.click(screen.getByText('\u00D7'))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/HelpPanel.test.tsx`
Expected: FAIL — `../HelpPanel` module not found

**Step 3: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/__tests__/HelpPanel.test.tsx
git commit -m "test: add failing tests for shared HelpPanel component"
```

---

### Task 2: Shared HelpPanel Component — Implementation

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/HelpPanel.tsx`

**Step 1: Implement the shared HelpPanel**

```tsx
interface HelpPanelProps {
  onClose: () => void
  quickStart: string[]
  faq: { q: string; a: string }[]
  shortcuts: { label: string; key: string }[]
}

export default function HelpPanel({ onClose, quickStart, faq, shortcuts }: HelpPanelProps) {
  return (
    <div className="fixed inset-y-0 right-0 w-[400px] bg-surface-1 border-l border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">Help</h2>
        <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg">&times;</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6 text-sm">
        {/* Quick Start */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Quick Start</h3>
          <ol className="list-decimal list-inside space-y-1 text-text-secondary">
            {quickStart.map((step, i) => (
              <li key={i} dangerouslySetInnerHTML={{ __html: step }} />
            ))}
          </ol>
        </section>

        {/* FAQ */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">FAQ</h3>
          <div className="space-y-3">
            {faq.map((item, i) => (
              <div key={i}>
                <p className="text-text-primary font-medium" dangerouslySetInnerHTML={{ __html: item.q }} />
                <p className="text-text-dim" dangerouslySetInnerHTML={{ __html: item.a }} />
              </div>
            ))}
          </div>
        </section>

        {/* Keyboard Shortcuts */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Keyboard Shortcuts</h3>
          <div className="space-y-1 text-text-secondary">
            {shortcuts.map((s, i) => (
              <div key={i} className="flex justify-between">
                <span>{s.label}</span>
                <kbd className="bg-surface-2 border border-border px-1.5 rounded text-xs font-mono">{s.key}</kbd>
              </div>
            ))}
          </div>
        </section>

        {/* Experimental notice */}
        <section className="bg-amber/5 border border-amber/20 rounded p-3 text-xs text-amber">
          This is experimental software. Features may change or break. Please report issues.
        </section>
      </div>
    </div>
  )
}
```

**Step 2: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/HelpPanel.test.tsx`
Expected: All 8 tests PASS

**Step 3: Export from barrel**

Edit `src/shesha/experimental/shared/frontend/src/index.ts` — add after the existing Header export:

```ts
export { default as HelpPanel } from './components/HelpPanel'
```

**Step 4: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/HelpPanel.tsx \
        src/shesha/experimental/shared/frontend/src/index.ts
git commit -m "feat: add shared HelpPanel component"
```

---

### Task 3: Add `onHelpToggle` to Shared Header — Tests

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/Header.test.tsx`

**Step 1: Add failing tests to the existing Header test file**

Append these tests inside the existing `describe('Header (shared)', ...)` block:

```tsx
  it('renders help button when onHelpToggle is provided', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} onHelpToggle={() => {}} />
    )
    const btn = screen.getByRole('button', { name: 'Help' })
    expect(btn).toHaveAttribute('data-tooltip', 'Help')
  })

  it('does not render help button when onHelpToggle is omitted', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    expect(screen.queryByRole('button', { name: 'Help' })).not.toBeInTheDocument()
  })

  it('calls onHelpToggle when help button is clicked', async () => {
    const onHelpToggle = vi.fn()
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} onHelpToggle={onHelpToggle} />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Help' }))
    expect(onHelpToggle).toHaveBeenCalledOnce()
  })
```

**Step 2: Run tests to verify new tests fail**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/Header.test.tsx`
Expected: 3 new tests FAIL (help button not rendered; `onHelpToggle` not a valid prop)

Note: The existing test `'renders without children (no app-specific buttons)'` expects exactly 1 button (theme toggle). This will still pass since `onHelpToggle` is omitted in that test.

**Step 3: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/__tests__/Header.test.tsx
git commit -m "test: add failing tests for help button in shared Header"
```

---

### Task 4: Add `onHelpToggle` to Shared Header — Implementation

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/Header.tsx`

**Step 1: Add `onHelpToggle` prop and render the `?` button**

Add `onHelpToggle?: () => void` to `HeaderProps`. Render the help button between `children` and the divider/theme-toggle area:

In the `HeaderProps` interface, add:
```ts
  onHelpToggle?: () => void
```

In the function signature, add `onHelpToggle` to destructuring.

In the JSX, inside `<div className="flex items-center gap-1">`, insert the help button after `{children}` and before the divider comment. The new structure should be:

```tsx
        {children}

        {/* Help button — shown when onHelpToggle is provided */}
        {onHelpToggle && (
          <button
            onClick={onHelpToggle}
            className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
            aria-label="Help"
            data-tooltip="Help"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
        )}

        {/* Divider - only show if there are children or help button */}
        {(children || onHelpToggle) && <div className="w-px h-6 bg-border mx-1" />}
```

Note: Update the divider condition from `{children && ...}` to `{(children || onHelpToggle) && ...}` so the divider shows when only the help button is present.

Also update the existing test `'renders without children (no app-specific buttons)'` — it still expects 1 button since no `onHelpToggle` is passed.

**Step 2: Run all Header tests**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/Header.test.tsx`
Expected: All tests PASS (including the 3 new ones)

**Step 3: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/Header.tsx
git commit -m "feat: add optional onHelpToggle prop to shared Header"
```

---

### Task 5: Wire Help into Code Explorer

**Files:**
- Modify: `src/shesha/experimental/code_explorer/frontend/src/App.tsx`

**Step 1: Add helpOpen state and HelpPanel**

At the top of `App.tsx`, add `HelpPanel` to the shared-ui import:

```ts
import {
  AppShell,
  Header,
  HelpPanel,
  TopicSidebar,
  // ... rest unchanged
} from '@shesha/shared-ui'
```

Inside `App()`, add state after `const [reposVersion, setReposVersion] = useState(0)`:

```ts
const [helpOpen, setHelpOpen] = useState(false)
```

In the `<Header>` JSX, add `onHelpToggle`:

```tsx
<Header appName="Code Explorer" isDark={dark} onToggleTheme={toggleTheme} onHelpToggle={() => setHelpOpen(h => !h)}>
```

Before `<ToastContainer />` at the end of the return, add:

```tsx
      {helpOpen && (
        <HelpPanel
          onClose={() => setHelpOpen(false)}
          quickStart={[
            'Create a topic using the <strong>+</strong> button in the sidebar',
            'Click <strong>+ Repo</strong> and paste a GitHub URL',
            'Wait for the analysis to complete \u2014 you can check status in the sidebar',
            'Select repositories using the checkboxes, then ask questions in the chat',
            'Click <strong>View trace</strong> on any answer to see how the LLM explored the code',
          ]}
          faq={[
            { q: 'What does the analysis status mean?', a: '<strong>Current</strong> means the analysis reflects the latest commit. <strong>Stale</strong> means new commits exist \u2014 click \u201cCheck for Updates\u201d to refresh. <strong>Missing</strong> means no analysis yet \u2014 click \u201cGenerate Analysis.\u201d' },
            { q: 'How do I update a repository\u2019s analysis?', a: 'Open the repository detail view and click \u201cCheck for Updates.\u201d If new commits are found, the analysis is regenerated automatically.' },
            { q: 'Can a repository belong to multiple topics?', a: 'Yes. Use the context menu on a repository to add it to additional topics.' },
            { q: 'What does the context budget indicator mean?', a: 'It estimates how much of the model\u2019s context window is used by your repositories and conversation. Green (&lt;50%), amber (&lt;80%), red (\u226580%).' },
            { q: 'Why do queries take so long?', a: 'Shesha uses a recursive approach: the LLM writes code to explore your repositories, runs it, examines the output, and repeats. This takes multiple iterations.' },
          ]}
          shortcuts={[
            { label: 'Send message', key: 'Enter' },
            { label: 'New line in input', key: 'Shift+Enter' },
            { label: 'Cancel query', key: 'Escape' },
          ]}
        />
      )}
```

**Step 2: Run the code-explorer frontend tests to verify nothing is broken**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/App.tsx
git commit -m "feat(code-explorer): add help panel with customized content"
```

---

### Task 6: Wire Help into Document Explorer

**Files:**
- Modify: `src/shesha/experimental/document_explorer/frontend/src/App.tsx`

**Step 1: Add helpOpen state and HelpPanel**

At the top of `App.tsx`, add `HelpPanel` to the shared-ui import:

```ts
import {
  AppShell,
  Header,
  HelpPanel,
  TopicSidebar,
  // ... rest unchanged
} from '@shesha/shared-ui'
```

Inside `App()`, add state after `const [docsVersion, setDocsVersion] = useState(0)`:

```ts
const [helpOpen, setHelpOpen] = useState(false)
```

In the `<Header>` JSX, add `onHelpToggle`:

```tsx
<Header appName="Document Explorer" isDark={dark} onToggleTheme={toggleTheme} onHelpToggle={() => setHelpOpen(h => !h)}>
```

Before `<ToastContainer />`, add:

```tsx
      {helpOpen && (
        <HelpPanel
          onClose={() => setHelpOpen(false)}
          quickStart={[
            'Create a topic using the <strong>+</strong> button in the sidebar',
            'Click <strong>Upload</strong> and drag-and-drop or select files',
            'Organize documents into topics using the context menu',
            'Select documents using the checkboxes, then ask questions in the chat',
            'Click <strong>View trace</strong> on any answer to see how the LLM explored your documents',
          ]}
          faq={[
            { q: 'What file types can I upload?', a: 'PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), RTF, and any plain-text file \u2014 including Markdown, CSV, HTML, config files, and source code.' },
            { q: 'What are the \u201cSources\u201d shown below answers?', a: 'They list which documents the LLM consulted to produce the answer. Click a source tag to view that document\u2019s details.' },
            { q: 'Can a document belong to multiple topics?', a: 'Yes. Open the document detail view to see which topics it belongs to and add or remove it from others.' },
            { q: 'What does the context budget indicator mean?', a: 'It estimates how much of the model\u2019s context window is used by your documents and conversation. Green (&lt;50%), amber (&lt;80%), red (\u226580%).' },
            { q: 'Why do queries take so long?', a: 'Shesha uses a recursive approach: the LLM writes code to explore your documents, runs it, examines the output, and repeats. This takes multiple iterations.' },
          ]}
          shortcuts={[
            { label: 'Send message', key: 'Enter' },
            { label: 'New line in input', key: 'Shift+Enter' },
            { label: 'Cancel query', key: 'Escape' },
          ]}
        />
      )}
```

**Step 2: Run the document-explorer frontend tests to verify nothing is broken**

Run: `cd src/shesha/experimental/document_explorer/frontend && npx vitest run`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
git add src/shesha/experimental/document_explorer/frontend/src/App.tsx
git commit -m "feat(document-explorer): add help panel with customized content"
```

---

### Task 7: Migrate Arxiv Explorer to Shared HelpPanel

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/Header.tsx`
- Delete: `src/shesha/experimental/web/frontend/src/components/HelpPanel.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/__tests__/Header.test.tsx`

**Step 1: Update arxiv-explorer's Header — remove the help button**

In `web/frontend/src/components/Header.tsx`:
- Remove `onHelpToggle` from `ArxivHeaderProps` and the function destructuring
- Remove the help `<button>` (lines 52-61)
- Pass `onHelpToggle` through to `SharedHeader` instead — wait, the help button is now in the shared Header. So just remove the custom help button entirely and don't pass `onHelpToggle` here. The `onHelpToggle` will be passed directly to SharedHeader from App.tsx.

Updated `ArxivHeaderProps`:
```ts
interface ArxivHeaderProps {
  onSearchToggle: () => void
  onCheckCitations: () => void
  onExport: () => void
  onHelpToggle: () => void
  dark: boolean
  onThemeToggle: () => void
}
```

Updated Header component — pass `onHelpToggle` through to SharedHeader:
```tsx
export default function Header({
  onSearchToggle,
  onCheckCitations,
  onExport,
  onHelpToggle,
  dark,
  onThemeToggle,
}: ArxivHeaderProps) {
  return (
    <SharedHeader appName="arXiv Explorer" isDark={dark} onToggleTheme={onThemeToggle} onHelpToggle={onHelpToggle}>
      <button
        onClick={onSearchToggle}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Search arXiv"
        data-tooltip="Search arXiv"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </button>
      <button
        onClick={onCheckCitations}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Check citations"
        data-tooltip="Check citations"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>
      <button
        onClick={onExport}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Export transcript"
        data-tooltip="Export transcript"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </button>
    </SharedHeader>
  )
}
```

**Step 2: Update arxiv-explorer's App.tsx — use shared HelpPanel**

Replace the local HelpPanel import:
```ts
// Remove this line:
import HelpPanel from './components/HelpPanel'
// Add to the @shesha/shared-ui import:
import { ..., HelpPanel } from '@shesha/shared-ui'
```

Replace the HelpPanel usage (line 314 area):
```tsx
      {helpOpen && (
        <HelpPanel
          onClose={() => setHelpOpen(false)}
          quickStart={[
            'Create a topic using the <strong>+</strong> button in the sidebar',
            'Click the <strong>Search</strong> icon to find papers on arXiv',
            'Select papers and click <strong>Add</strong> to add them to your topic',
            'Ask questions about your papers in the chat area',
            'Click <strong>View trace</strong> on any answer to see how the LLM arrived at it',
          ]}
          faq={[
            { q: 'How do I add papers to multiple topics?', a: 'Use the search panel\u2019s topic picker when adding papers. Each paper can belong to multiple topics.' },
            { q: 'What does the context budget indicator mean?', a: 'It estimates how much of the model\u2019s context window is used by your documents and conversation history. Green (&lt;50%), amber (&lt;80%), red (\u226580%).' },
            { q: 'Why do queries take so long?', a: 'Shesha uses a recursive approach: the LLM writes code to explore your documents, runs it, examines the output, and repeats. This takes multiple iterations.' },
            { q: 'Can I cancel a running query?', a: 'Yes, press Escape or click the cancel button while a query is running.' },
            { q: 'What is the citation check?', a: 'It verifies that claims in the LLM\u2019s answer are supported by the source documents. Results show which citations are verified, unverified, or missing.' },
            { q: 'How do I export my conversation?', a: 'Click the export button in the header to download a Markdown transcript of the current topic\u2019s conversation.' },
          ]}
          shortcuts={[
            { label: 'Send message', key: 'Enter' },
            { label: 'New line in input', key: 'Shift+Enter' },
            { label: 'Cancel query', key: 'Escape' },
          ]}
        />
      )}
```

**Step 3: Update arxiv-explorer Header tests**

In `web/frontend/src/components/__tests__/Header.test.tsx`, the existing test checks for a "Help" button rendered by the arxiv Header. Since the help button is now rendered by the shared Header (via `onHelpToggle` prop passthrough), the test should still find it.

Update `defaultProps` — keep `onHelpToggle`:
```ts
const defaultProps = {
  onSearchToggle: vi.fn(),
  onCheckCitations: vi.fn(),
  onExport: vi.fn(),
  onHelpToggle: vi.fn(),
  dark: true,
  onThemeToggle: vi.fn(),
}
```

The "renders tooltip for help button" test should still pass since the shared Header renders the `?` button when `onHelpToggle` is provided.

**Step 4: Delete the old HelpPanel**

```bash
rm src/shesha/experimental/web/frontend/src/components/HelpPanel.tsx
```

**Step 5: Run all arxiv-explorer frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All tests PASS

**Step 6: Commit**

```bash
git rm src/shesha/experimental/web/frontend/src/components/HelpPanel.tsx
git add src/shesha/experimental/web/frontend/src/App.tsx \
        src/shesha/experimental/web/frontend/src/components/Header.tsx \
        src/shesha/experimental/web/frontend/src/components/__tests__/Header.test.tsx
git commit -m "refactor(arxiv-explorer): migrate to shared HelpPanel component"
```

---

### Task 8: Run All Frontend Tests

**Files:** None (verification only)

**Step 1: Run shared frontend tests**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run`
Expected: All tests PASS

**Step 2: Run arxiv-explorer frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All tests PASS

**Step 3: Run code-explorer frontend tests**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All tests PASS

**Step 4: Run document-explorer frontend tests**

Run: `cd src/shesha/experimental/document_explorer/frontend && npx vitest run`
Expected: All tests PASS

---

### Task 9: Update Changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under `[Unreleased]`**

Under the **Added** section:
```
- Help panel (`?` button) for Code Explorer and Document Explorer with customized quick-start guides, FAQs, and keyboard shortcuts
```

Under the **Changed** section:
```
- Refactored arxiv-explorer help panel to use shared HelpPanel component
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for shared help panel"
```
