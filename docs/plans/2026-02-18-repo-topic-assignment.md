# Repo-to-Topic Assignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a context menu on document rows in TopicSidebar so users can assign repos to topics (and remove them) without re-adding.

**Architecture:** Two new optional callback props on TopicSidebar (`addDocToTopic`, `removeDocFromTopic`) gate the feature. When provided, each doc row gets an ellipsis menu showing "Add to..." with a topic submenu and (when inside a topic) "Remove from [Topic]". Code-explorer wires callbacks to existing `topicRepos` API endpoints.

**Tech Stack:** React, TypeScript, Vitest, @testing-library/react. Tailwind CSS for styling.

---

### Task 1: Add new props to TopicSidebar (types only)

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx` (lines 7-25, the `TopicSidebarProps` interface)

**Step 1: Write the failing test**

Add to `src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx`:

```tsx
it('does not render doc menu button when addDocToTopic is not provided', async () => {
  const props = defaultProps({
    activeTopic: 'chess',
    loadDocuments: vi.fn().mockResolvedValue(chessDocs),
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('Chess Strategies')
  // No ellipsis menu buttons should exist on document rows
  const docRows = screen.getByText('Chess Strategies').closest('div[class*="flex"]')!
  const buttons = within(docRows as HTMLElement).queryAllByRole('button')
  // Only the checkbox-adjacent elements — no menu button
  expect(buttons).toHaveLength(0)
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "does not render doc menu button"`

Expected: PASS (this is a guard test — it should already pass since there's no menu button yet). If it passes, that's correct — we're establishing the baseline.

**Step 3: Write a second test that will actually fail**

Add to the same test file:

```tsx
it('renders doc menu button when addDocToTopic is provided', async () => {
  const props = defaultProps({
    activeTopic: 'chess',
    loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    addDocToTopic: vi.fn(),
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('Chess Strategies')
  // Each doc row should have an ellipsis menu button
  const menuButtons = screen.getAllByTitle('Document actions')
  expect(menuButtons.length).toBeGreaterThanOrEqual(2) // 2 chess docs
})
```

**Step 4: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "renders doc menu button"`

Expected: FAIL — `addDocToTopic` is not a known prop yet, and no menu button is rendered.

**Step 5: Add the props to the interface and render ellipsis button**

In `TopicSidebar.tsx`, add to the `TopicSidebarProps` interface:

```tsx
addDocToTopic?: (docId: string, topicName: string) => Promise<void>
removeDocFromTopic?: (docId: string, topicName: string) => Promise<void>
```

Destructure both in the component function signature.

In `renderDocList`, after the `<span>` for `doc.label`, add (still inside the doc row div):

```tsx
{addDocToTopic && (
  <button
    title="Document actions"
    onClick={e => e.stopPropagation()}
    className="ml-auto opacity-0 group-hover:opacity-100 text-text-dim hover:text-text-secondary transition-opacity text-xs px-1"
  >
    &hellip;
  </button>
)}
```

Add the `group` class to the doc row div (the one with `flex items-center gap-1`).

Do the same for uncategorized doc rows.

**Step 6: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx`

Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx \
       src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx
git commit -m "feat: add addDocToTopic/removeDocFromTopic props with ellipsis button"
```

---

### Task 2: Document context menu — "Add to..." submenu

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx`
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx`

**Step 1: Write the failing test**

```tsx
it('shows "Add to..." submenu with available topics when doc menu is clicked', async () => {
  const addDocToTopic = vi.fn()
  const props = defaultProps({
    activeTopic: 'chess',
    loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    addDocToTopic,
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('Chess Strategies')
  const menuButtons = screen.getAllByTitle('Document actions')
  await userEvent.click(menuButtons[0])

  // Should show "Add to..." menu item
  expect(screen.getByText('Add to\u2026')).toBeInTheDocument()
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "shows .Add to"`

Expected: FAIL — clicking ellipsis does nothing yet.

**Step 3: Implement the context menu**

Add state to the component:

```tsx
const [docMenuOpen, setDocMenuOpen] = useState<string | null>(null) // doc id
const [docSubmenuOpen, setDocSubmenuOpen] = useState(false)
```

Replace the placeholder ellipsis button `onClick` to toggle `docMenuOpen`:

```tsx
onClick={e => {
  e.stopPropagation()
  setDocMenuOpen(docMenuOpen === doc.id ? null : doc.id)
  setDocSubmenuOpen(false)
}}
```

After the ellipsis button (inside the same doc row, using `relative` on the row), render:

```tsx
{docMenuOpen === doc.id && (
  <div className="absolute right-0 top-full z-20 bg-surface-2 border border-border rounded shadow-lg text-xs min-w-[140px]">
    {addDocToTopic && topics.length > 0 && (
      <div
        className="relative"
        onMouseEnter={() => setDocSubmenuOpen(true)}
        onMouseLeave={() => setDocSubmenuOpen(false)}
      >
        <button
          className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
          onClick={e => {
            e.stopPropagation()
            setDocSubmenuOpen(!docSubmenuOpen)
          }}
        >
          Add to&hellip;
        </button>
        {docSubmenuOpen && (
          <div className="absolute left-full top-0 z-30 bg-surface-2 border border-border rounded shadow-lg text-xs min-w-[120px]">
            {topics
              .filter(t => {
                const docs = topicDocs[t.name]
                return !docs || !docs.some(d => d.id === doc.id)
              })
              .map(t => (
                <button
                  key={t.name}
                  className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
                  onClick={async e => {
                    e.stopPropagation()
                    try {
                      await addDocToTopic(doc.id, t.name)
                      showToast(`Added to ${t.name}`, 'success')
                    } catch {
                      showToast(`Failed to add to ${t.name}`, 'error')
                    }
                    setDocMenuOpen(null)
                  }}
                >
                  {t.name}
                </button>
              ))}
          </div>
        )}
      </div>
    )}
  </div>
)}
```

Make the doc row div `relative` (add to className).

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx \
       src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx
git commit -m "feat: add 'Add to...' submenu on document context menu"
```

---

### Task 3: Document context menu — "Add to..." calls callback

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx`

**Step 1: Write the failing test**

```tsx
it('calls addDocToTopic when a topic is selected from submenu', async () => {
  const addDocToTopic = vi.fn().mockResolvedValue(undefined)
  const loadDocuments = vi.fn()
    .mockImplementation((name: string) =>
      Promise.resolve(name === 'chess' ? chessDocs : [])
    )
  const props = defaultProps({
    activeTopic: 'chess',
    loadDocuments,
    addDocToTopic,
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('Chess Strategies')
  const menuButtons = screen.getAllByTitle('Document actions')
  await userEvent.click(menuButtons[0])
  // Hover or click "Add to..." to open submenu
  await userEvent.click(screen.getByText('Add to\u2026'))
  // "math" should appear as an option (chess doc is not in math)
  await userEvent.click(screen.getByText('math'))

  expect(addDocToTopic).toHaveBeenCalledWith('doc-1', 'math')
})
```

**Step 2: Run test to verify it passes**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "calls addDocToTopic"`

Expected: PASS (implementation from Task 2 should already handle this). If it fails, adjust the menu click interaction (may need `userEvent.hover` instead of click for submenu).

**Step 3: Commit (if new test code added)**

```bash
git add src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx
git commit -m "test: verify addDocToTopic callback fires from submenu"
```

---

### Task 4: Document context menu — "Remove from [Topic]"

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx`
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx`

**Step 1: Write the failing test**

```tsx
it('shows "Remove from [topic]" for docs inside a topic and calls removeDocFromTopic', async () => {
  const removeDocFromTopic = vi.fn().mockResolvedValue(undefined)
  const props = defaultProps({
    activeTopic: 'chess',
    loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    addDocToTopic: vi.fn(),
    removeDocFromTopic,
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('Chess Strategies')
  const menuButtons = screen.getAllByTitle('Document actions')
  await userEvent.click(menuButtons[0])

  const removeBtn = screen.getByText('Remove from chess')
  await userEvent.click(removeBtn)

  expect(removeDocFromTopic).toHaveBeenCalledWith('doc-1', 'chess')
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "Remove from"`

Expected: FAIL — no "Remove from chess" button exists yet.

**Step 3: Add "Remove from [Topic]" to the menu**

In the document context menu div (rendered when `docMenuOpen === doc.id`), after the "Add to..." block, add:

```tsx
{removeDocFromTopic && topicName && (
  <button
    className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-red"
    onClick={async e => {
      e.stopPropagation()
      try {
        await removeDocFromTopic(doc.id, topicName)
        showToast(`Removed from ${topicName}`, 'success')
      } catch {
        showToast(`Failed to remove from ${topicName}`, 'error')
      }
      setDocMenuOpen(null)
    }}
  >
    Remove from {topicName}
  </button>
)}
```

Note: `renderDocList` already receives `topicName` as a parameter. For uncategorized docs, we don't pass `topicName`, so the "Remove" item won't appear there — which is correct.

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx \
       src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx
git commit -m "feat: add 'Remove from [topic]' to document context menu"
```

---

### Task 5: Uncategorized docs also get the context menu

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx`
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx`

**Step 1: Write the failing test**

```tsx
it('renders doc menu on uncategorized docs with only "Add to..." (no remove)', async () => {
  const addDocToTopic = vi.fn().mockResolvedValue(undefined)
  const uncatDocs: DocumentItem[] = [
    { id: 'uncat-1', label: 'Orphan Doc' },
  ]
  const props = defaultProps({
    uncategorizedDocs: uncatDocs,
    addDocToTopic,
  })
  render(<TopicSidebar {...props} />)

  await screen.findByText('chess') // wait for topics to load
  const menuBtn = screen.getByTitle('Document actions')
  await userEvent.click(menuBtn)

  expect(screen.getByText('Add to\u2026')).toBeInTheDocument()
  expect(screen.queryByText(/Remove from/)).not.toBeInTheDocument()
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx -t "uncategorized docs"`

Expected: FAIL — uncategorized doc rows don't have the menu yet.

**Step 3: Add context menu to uncategorized section**

In the uncategorized docs section (around line 346-382 in current code), apply the same pattern as `renderDocList`:
- Add `group relative` class to the doc row div
- Add the ellipsis button (gated on `addDocToTopic`)
- Render the same context menu dropdown, but pass `topicName` as `null` or `undefined` so "Remove" doesn't appear

The cleanest approach: extract the doc row + menu into a helper that `renderDocList` and the uncategorized section both call, taking `topicName: string | null` to control the "Remove" option.

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TopicSidebar.test.tsx`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx \
       src/shesha/experimental/shared/frontend/src/components/__tests__/TopicSidebar.test.tsx
git commit -m "feat: add context menu to uncategorized document rows"
```

---

### Task 6: Wire up in code-explorer App.tsx

**Files:**
- Modify: `src/shesha/experimental/code_explorer/frontend/src/App.tsx` (around line 214-240, TopicSidebar props)
- Modify: `src/shesha/experimental/code_explorer/frontend/src/__tests__/App.test.tsx`

**Step 1: Write the failing test**

Add to `App.test.tsx`:

```tsx
it('passes addDocToTopic and removeDocFromTopic to TopicSidebar', async () => {
  render(<App />)
  await flush()
  // The sidebar is rendered — verify the API is called when the callbacks fire.
  // We can't easily test prop passing without inspecting the component tree,
  // so instead test the end-to-end: trigger the callback and verify API call.
  // For now, just verify the app renders without error with the new props.
  expect(screen.getByText('Code Explorer')).toBeInTheDocument()
})
```

This is a smoke test. The real integration test is that TopicSidebar's own tests cover the callback behavior.

**Step 2: Add the callbacks to App.tsx**

After `handleRemoveRepo` (around line 162), add:

```tsx
const handleAddDocToTopic = useCallback(async (docId: string, topicName: string) => {
  await api.topicRepos.add(topicName, docId)
  setReposVersion(v => v + 1)
}, [])

const handleRemoveDocFromTopic = useCallback(async (docId: string, topicName: string) => {
  await api.topicRepos.remove(topicName, docId)
  setReposVersion(v => v + 1)
}, [])
```

Pass to TopicSidebar:

```tsx
addDocToTopic={handleAddDocToTopic}
removeDocFromTopic={handleRemoveDocFromTopic}
```

**Step 3: Run all frontend tests**

Run:
```bash
cd src/shesha/experimental/code_explorer/frontend && npx vitest run
cd src/shesha/experimental/shared/frontend && npx vitest run
```

Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/App.tsx \
       src/shesha/experimental/code_explorer/frontend/src/__tests__/App.test.tsx
git commit -m "feat: wire addDocToTopic/removeDocFromTopic in code-explorer App"
```

---

### Task 7: Full suite verification and changelog

**Step 1: Run full test suite**

```bash
make all
cd src/shesha/experimental/shared/frontend && npx vitest run
cd src/shesha/experimental/code_explorer/frontend && npx vitest run
cd src/shesha/experimental/web/frontend && npx vitest run
```

Expected: ALL PASS, no regressions in any frontend.

**Step 2: Update CHANGELOG.md**

Add under `[Unreleased]` → `Added`:

```
- Context menu on sidebar repos to add/remove from topics (code explorer)
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for repo-topic context menu"
```
