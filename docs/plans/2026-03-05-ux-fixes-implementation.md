# UX Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three UX issues: auto-growing input textarea, markdown rendering for user messages, and per-topic chat history in code explorer.

**Architecture:** All changes to the textarea and message rendering go in the shared frontend components (`@shesha/shared-ui`), benefiting all tools. Per-topic chat is a code-explorer-only backend+frontend wiring change — the shared routes already support it.

**Tech Stack:** React 19, TypeScript, Vitest, react-markdown, FastAPI, pytest

---

### Task 1: Auto-Growing Textarea — Test

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`

**Step 1: Write the failing test**

Add a new `describe` block at the end of the file:

```tsx
describe('ChatArea (shared) - auto-growing textarea', () => {
  const baseProps = {
    topicName: 'chess',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
    selectedDocuments: new Set(['doc-1']),
    loadHistory: vi.fn().mockResolvedValue([]),
  }

  it('textarea grows height when content changes', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ChatArea {...baseProps} />)
    })

    const textarea = screen.getByPlaceholderText('Ask a question...') as HTMLTextAreaElement

    // Simulate multi-line input
    await user.type(textarea, 'Line 1\nLine 2\nLine 3')

    // The textarea should have an inline style.height set (auto-grow applied)
    expect(textarea.style.height).not.toBe('')
  })

  it('textarea has max-height to cap growth', async () => {
    await act(async () => {
      render(<ChatArea {...baseProps} />)
    })

    const textarea = screen.getByPlaceholderText('Ask a question...') as HTMLTextAreaElement
    expect(textarea.style.maxHeight).toBe('6rem')
  })

  it('textarea resets height after sending', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ChatArea {...baseProps} />)
    })

    const textarea = screen.getByPlaceholderText('Ask a question...') as HTMLTextAreaElement
    await user.type(textarea, 'Line 1\nLine 2')
    await user.click(screen.getByText('Send'))

    // After send, input is cleared, height should reset
    expect(textarea.value).toBe('')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: FAIL — textarea has no inline style.height or style.maxHeight

---

### Task 2: Auto-Growing Textarea — Implementation

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx`

**Step 1: Add textarea ref and auto-resize effect**

Add a ref for the textarea (after the existing `scrollRef` on line 49):

```tsx
const textareaRef = useRef<HTMLTextAreaElement>(null)
```

Add a `useEffect` after the auto-scroll effect (after line 99):

```tsx
// Auto-resize textarea to fit content, up to ~4 lines
useEffect(() => {
  const el = textareaRef.current
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, el.offsetHeight || el.scrollHeight)}px`
}, [input])
```

**Step 2: Wire the ref and styles to the textarea element**

Replace the existing `<textarea` element (lines 193-205) with:

```tsx
<textarea
  ref={textareaRef}
  value={input}
  onChange={e => setInput(e.target.value)}
  onKeyDown={handleKeyDown}
  disabled={!connected || !hasDocuments}
  placeholder={
    !connected ? 'Reconnecting...'
    : !hasDocuments ? emptySelectionMessage
    : placeholder
  }
  rows={1}
  style={{ maxHeight: '6rem' }}
  className="flex-1 bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary resize-none overflow-y-auto focus:outline-none focus:border-accent disabled:opacity-50"
/>
```

Key changes:
- Added `ref={textareaRef}`
- Added `style={{ maxHeight: '6rem' }}`
- Added `overflow-y-auto` to className (replaces implicit overflow)
- Kept `resize-none` (user shouldn't manually drag-resize; auto-grow handles it)

**Step 3: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx \
        src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx
git commit -m "feat: auto-grow textarea input up to 4 lines"
```

---

### Task 3: Markdown User Messages — Test

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatMessage.test.tsx`

**Step 1: Write the failing test**

Add a new `describe` block at the end of the file:

```tsx
describe('ChatMessage (shared) - user question markdown', () => {
  it('renders markdown formatting in user questions', () => {
    const exchange = {
      ...baseExchange,
      question: '## My Heading\n\n- item one\n- item two',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    // The question bubble should render markdown, not raw text
    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveTextContent('My Heading')
    const items = screen.getAllByRole('listitem')
    expect(items.length).toBeGreaterThanOrEqual(2)
  })

  it('renders code blocks in user questions', () => {
    const exchange = {
      ...baseExchange,
      question: 'Check this:\n\n```python\nprint("hello")\n```',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByText('print("hello")')).toBeInTheDocument()
  })

  it('does not apply stripBoundaryMarkers to user questions', () => {
    const hex = 'bd0e753b7146bd0089d21bfab2c51ded'
    const exchange = {
      ...baseExchange,
      question: `UNTRUSTED_CONTENT_${hex}_BEGIN\nsome text\nUNTRUSTED_CONTENT_${hex}_END`,
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    // Boundary markers in questions should NOT be stripped (they only come from assistant)
    // The raw text should appear (react-markdown will render it as paragraphs)
    expect(screen.queryByText('Quoted content')).not.toBeInTheDocument()
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: FAIL — question is rendered as plain text, no heading/list roles found

---

### Task 4: Markdown User Messages — Implementation

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx`

**Step 1: Replace plain text question with Markdown renderer**

Replace line 33-35 (the question content):

```tsx
        <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
          {exchange.question}
        </div>
```

With:

```tsx
        <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
          <Markdown components={mdComponents}>{exchange.question}</Markdown>
        </div>
```

No other changes needed — `Markdown` and `mdComponents` are already imported.

**Step 2: Also update the pending question in ChatArea.tsx**

The pending question bubble in `ChatArea.tsx` (line 167-169) also renders plain text. Update it:

Replace line 167-169:

```tsx
              <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
                {pendingQuestion}
              </div>
```

With:

```tsx
              <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
                <Markdown components={mdComponents}>{pendingQuestion}</Markdown>
              </div>
```

Add the import at the top of ChatArea.tsx (after the existing imports):

```tsx
import Markdown from 'react-markdown'
import { mdComponents } from './mdComponents'
```

**Step 3: Update existing test that checks for plain text question rendering**

In `ChatMessage.test.tsx`, the test "renders the question text" (line 20-25) searches for exact text. Since markdown wraps text in `<p>` tags, the text will still be found by `getByText` — no change needed.

However, test line 27 "renders the answer text as plain text by default" description is now misleading. The answer was already rendered via markdown. No code change needed, but note the description is about answers, not questions.

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: PASS

Also run ChatArea tests to make sure pending question still works:

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatArea.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx \
        src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx \
        src/shesha/experimental/shared/frontend/src/components/__tests__/ChatMessage.test.tsx
git commit -m "feat: render user messages as markdown"
```

---

### Task 5: Per-Topic History — Backend Test

**Files:**
- Create: `tests/experimental/code_explorer/test_api_history.py`

**Step 1: Write the failing test**

```python
"""Tests for per-topic conversation history in code explorer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import CodeExplorerState
from shesha.experimental.code_explorer.topics import CodeExplorerTopicManager
from shesha.experimental.shared.session import WebConversationSession


@pytest.fixture()
def state(tmp_path: Path) -> CodeExplorerState:
    shesha = MagicMock()
    shesha.list_projects.return_value = []
    shesha._storage = MagicMock()
    shesha._storage.list_traces.return_value = []

    topics_dir = tmp_path / "topics"
    topics_dir.mkdir()
    topic_mgr = CodeExplorerTopicManager(topics_dir)
    topic_mgr.create("Alpha")
    topic_mgr.create("Beta")

    session = WebConversationSession(tmp_path)
    return CodeExplorerState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        session=session,
        model="test-model",
    )


@pytest.fixture()
def client(state: CodeExplorerState) -> TestClient:
    app = create_api(state)
    return TestClient(app)


class TestPerTopicHistory:
    def test_topics_have_independent_history(
        self, client: TestClient, state: CodeExplorerState
    ) -> None:
        """Each topic should have its own conversation history."""
        # History for Alpha and Beta should be independent
        resp_a = client.get("/api/topics/Alpha/history")
        assert resp_a.status_code == 200
        assert resp_a.json()["exchanges"] == []

        resp_b = client.get("/api/topics/Beta/history")
        assert resp_b.status_code == 200
        assert resp_b.json()["exchanges"] == []

    def test_clear_only_affects_target_topic(
        self, client: TestClient, state: CodeExplorerState, tmp_path: Path
    ) -> None:
        """Clearing one topic's history should not affect another."""
        # Manually add an exchange to Alpha's session
        alpha_session = _get_topic_session(state, "Alpha")
        alpha_session.add_exchange(
            question="Q1",
            answer="A1",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        beta_session = _get_topic_session(state, "Beta")
        beta_session.add_exchange(
            question="Q2",
            answer="A2",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        # Clear Alpha
        resp = client.delete("/api/topics/Alpha/history")
        assert resp.status_code == 200

        # Alpha should be empty
        resp_a = client.get("/api/topics/Alpha/history")
        assert resp_a.json()["exchanges"] == []

        # Beta should still have its exchange
        resp_b = client.get("/api/topics/Beta/history")
        assert len(resp_b.json()["exchanges"]) == 1

    def test_global_history_routes_removed(
        self, client: TestClient
    ) -> None:
        """The old global /api/history endpoint should no longer exist."""
        resp = client.get("/api/history")
        assert resp.status_code == 404

        resp = client.delete("/api/history")
        assert resp.status_code == 404


def _get_topic_session(
    state: CodeExplorerState, topic_name: str
) -> WebConversationSession:
    """Helper to create a per-topic session the same way the API does."""
    meta, meta_path = state.topic_mgr._resolve(topic_name)
    topic_dir = meta_path.parent
    return WebConversationSession(topic_dir)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/code_explorer/test_api_history.py -v`
Expected: FAIL — `_get_global_session` returns the same session for all topics; global `/api/history` still exists

---

### Task 6: Per-Topic History — Backend Implementation

**Files:**
- Modify: `src/shesha/experimental/code_explorer/api.py`
- Modify: `src/shesha/experimental/code_explorer/websockets.py`

**Step 1: Change session callback in api.py**

Replace `_get_global_session` (lines 52-54):

```python
def _get_global_session(state: CodeExplorerState, topic_name: str) -> WebConversationSession:
    """Return the global session (code explorer has one session, not per-topic)."""
    return state.session
```

With:

```python
def _get_topic_session(state: CodeExplorerState, topic_name: str) -> WebConversationSession:
    """Return a per-topic session stored in the topic's directory."""
    meta, meta_path = state.topic_mgr._resolve(topic_name)
    topic_dir = meta_path.parent
    return WebConversationSession(topic_dir)
```

Update the `create_shared_router` call (line 279):

```python
get_session=lambda s, name: _get_topic_session(state, name),
```

**Step 2: Remove global history routes from `_create_repo_router`**

Delete lines 251-269 (the "Global history routes" section including `/history` GET, DELETE, and `/export` GET). The shared router's per-topic routes at `/api/topics/{name}/history` and `/api/topics/{name}/export` replace them.

**Step 3: Update websockets.py to save to per-topic session**

In `websockets.py`, the query handler saves to `state.session` (line 177). The topic name is in `data.get("topic")`. Change lines 176-189:

Replace:

```python
    # Save to global session
    state.session.add_exchange(
```

With:

```python
    # Save to per-topic session
    topic_name = str(data.get("topic", ""))
    if topic_name:
        from shesha.experimental.code_explorer.api import _get_topic_session
        topic_session = _get_topic_session(state, topic_name)
    else:
        topic_session = state.session  # Fallback to global if no topic
    topic_session.add_exchange(
```

Also update the history prefix (line 89):

Replace:

```python
    history_prefix = state.session.format_history_prefix()
```

With:

```python
    topic_name = str(data.get("topic", ""))
    if topic_name:
        from shesha.experimental.code_explorer.api import _get_topic_session
        topic_session = _get_topic_session(state, topic_name)
    else:
        topic_session = state.session
    history_prefix = topic_session.format_history_prefix()
```

Note: To avoid the double import, refactor by moving `_get_topic_session` to a small helper or just import once at the top. The cleaner approach:

Move the function to `dependencies.py` (since it only uses `CodeExplorerState`):

In `dependencies.py`, add:

```python
def get_topic_session(state: CodeExplorerState, topic_name: str) -> WebConversationSession:
    """Return a per-topic session stored in the topic's directory."""
    meta, meta_path = state.topic_mgr._resolve(topic_name)
    topic_dir = meta_path.parent
    return WebConversationSession(topic_dir)
```

Then import from `dependencies` in both `api.py` and `websockets.py`.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/experimental/code_explorer/test_api_history.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py \
        src/shesha/experimental/code_explorer/websockets.py \
        src/shesha/experimental/code_explorer/dependencies.py \
        tests/experimental/code_explorer/test_api_history.py
git commit -m "feat: per-topic chat history for code explorer"
```

---

### Task 7: Per-Topic History — Frontend Test

**Files:**
- Modify: `src/shesha/experimental/code_explorer/frontend/src/api/__tests__/client.test.ts`

**Step 1: Write the failing test**

Replace the existing `describe('api.history', ...)` block (lines 130-147) with:

```ts
describe('api.history (per-topic)', () => {
  it('get fetches GET /api/topics/{name}/history', async () => {
    const api = await getApi()
    await api.history.get('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/history', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('get encodes topic name', async () => {
    const api = await getApi()
    await api.history.get('a topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic/history', expect.any(Object))
  })

  it('clear sends DELETE to /api/topics/{name}/history', async () => {
    const api = await getApi()
    await api.history.clear('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/history', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })
})

describe('api.export (per-topic)', () => {
  it('fetches GET /api/topics/{name}/export and returns text', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('exported markdown'),
    })

    const api = await getApi()
    const result = await api.export('my-topic')

    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/export')
    expect(result).toBe('exported markdown')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run src/api/__tests__/client.test.ts`
Expected: FAIL — `api.history.get()` doesn't accept a topic param; calls `/api/history` not `/api/topics/{name}/history`

---

### Task 8: Per-Topic History — Frontend Implementation

**Files:**
- Modify: `src/shesha/experimental/code_explorer/frontend/src/api/client.ts`
- Modify: `src/shesha/experimental/code_explorer/frontend/src/App.tsx`

**Step 1: Remove history override in client.ts**

In `client.ts`, delete the history override (lines 9-13):

```ts
  // Override history to be global (no topic parameter)
  history: {
    get: () => request<{ exchanges: Exchange[] }>('/history'),
    clear: () => request<{ status: string }>('/history', { method: 'DELETE' }),
  },
```

This makes `api.history` fall through to `sharedApi.history` which already uses per-topic endpoints.

Also remove the `Exchange` import from line 4 (now unused in this file):

```ts
import type { RepoInfo, RepoAnalysis, UpdateStatus } from '../types'
```

**Step 2: Update the export override to be per-topic**

Replace the export override (lines 16-20):

```ts
  // Override export to be global
  export: async () => {
    const resp = await fetch('/api/export')
    if (!resp.ok) throw new Error(resp.statusText)
    return resp.text()
  },
```

With:

```ts
  // Use shared per-topic export (re-export from sharedApi)
```

Actually, just delete the export override entirely — `sharedApi.export` already accepts a topic parameter. The spread `...sharedApi` will provide it.

**Step 3: Update App.tsx loadHistory and clearHistory callbacks**

Replace `loadHistory` (lines 174-178):

```tsx
  // Global history (ignores topic param since code explorer history is global)
  const loadHistory = useCallback(async (_topic: string): Promise<Exchange[]> => {
    const data = await api.history.get()
    return data.exchanges
  }, [])
```

With:

```tsx
  const loadHistory = useCallback(async (topic: string): Promise<Exchange[]> => {
    const data = await api.history.get(topic)
    return data.exchanges
  }, [])
```

Replace `handleClearHistory` (lines 180-189):

```tsx
  const handleClearHistory = useCallback(async () => {
    try {
      await api.history.clear()
      setHistoryVersion(v => v + 1)
      setTokens({ prompt: 0, completion: 0, total: 0 })
      showToast('Conversation cleared', 'success')
    } catch {
      showToast('Failed to clear conversation', 'error')
    }
  }, [setHistoryVersion, setTokens])
```

With:

```tsx
  const handleClearHistory = useCallback(async () => {
    if (!activeTopic) return
    try {
      await api.history.clear(activeTopic)
      setHistoryVersion(v => v + 1)
      setTokens({ prompt: 0, completion: 0, total: 0 })
      showToast('Conversation cleared', 'success')
    } catch {
      showToast('Failed to clear conversation', 'error')
    }
  }, [activeTopic, setHistoryVersion, setTokens])
```

Replace `handleExport` (lines 191-205):

```tsx
  const handleExport = useCallback(async () => {
    try {
      const content = await api.export()
```

With:

```tsx
  const handleExport = useCallback(async () => {
    if (!activeTopic) return
    try {
      const content = await api.export(activeTopic)
```

Update the dependency array to include `activeTopic`.

Remove the `Exchange` import from the types import (line 21) since it's no longer needed directly in App.tsx — check if it's still used elsewhere in the file. Looking at the code, `Exchange` is used in the `loadHistory` return type annotation. Actually the type annotation is inferred. Check: if `Exchange` is only used in the type of `loadHistory`, TypeScript can infer it from `api.history.get()`. But since it's in the import, it's fine to keep it or remove it if unused.

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/api/client.ts \
        src/shesha/experimental/code_explorer/frontend/src/App.tsx \
        src/shesha/experimental/code_explorer/frontend/src/api/__tests__/client.test.ts
git commit -m "feat: code explorer frontend uses per-topic history"
```

---

### Task 9: Run Full Test Suites

**Step 1: Run shared frontend tests**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run`
Expected: All tests pass

**Step 2: Run code explorer frontend tests**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All tests pass

**Step 3: Run backend tests**

Run: `make all`
Expected: Format, lint, typecheck, and all tests pass

**Step 4: Fix any issues found, then commit**

---

### Task 10: Update Docs & Changelog

**Files:**
- Modify: `docs/extending-web-tools.md` (if anything is outdated)
- Modify: `CHANGELOG.md`

**Step 1: Review extending-web-tools.md**

Check if the doc still accurately describes the history architecture. The doc currently says the code explorer uses a global session (line 201-203). Update if needed to reflect that per-topic history is now the standard pattern for all tools.

**Step 2: Add changelog entries**

Under `[Unreleased]`:

```markdown
### Changed
- Chat input area now auto-grows up to 4 lines as you type
- User messages in chat are now rendered as markdown (headers, code blocks, lists)
- Code explorer conversation history is now per-topic instead of global
```

**Step 3: Commit**

```bash
git add docs/extending-web-tools.md CHANGELOG.md
git commit -m "docs: update for UX fixes"
```
