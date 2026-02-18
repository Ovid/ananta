# Shared Code Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate ~800 lines of duplicated code between code-explorer and arxiv-explorer by making `create_shared_router()` actually usable and extracting a `useAppState` hook for frontends.

**Architecture:** Add callback parameters to the existing shared router so each tool can customize session access, topic listing, and project ID resolution without reimplementing all routes. On the frontend, extract common App.tsx state/handlers into a `useAppState` hook and move the connection-loss banner into `AppShell`.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Vitest (frontend), pytest (backend tests)

---

### Task 1: Make `create_shared_router()` accept callbacks

The shared router currently hardcodes session creation and topic listing. Add three callback parameters so tools can customize behavior without reimplementing routes.

**Files:**
- Modify: `src/shesha/experimental/shared/routes.py`
- Test: `tests/experimental/shared/test_shared_routes.py` (create)

**Step 1: Write failing tests for the callback parameters**

Create `tests/experimental/shared/test_shared_routes.py`:

```python
"""Tests for shared router callback parameters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shesha.experimental.shared.routes import create_shared_router
from shesha.experimental.shared.schemas import TopicInfo
from shesha.experimental.shared.session import WebConversationSession


def _make_state(tmp_path: Path) -> MagicMock:
    """Build a minimal mock state for the shared router."""
    state = MagicMock()
    state.model = "test-model"
    state.topic_mgr.list_topics.return_value = []
    state.topic_mgr.resolve.return_value = None
    state.topic_mgr._storage.list_traces.return_value = []
    return state


def _make_app(state: MagicMock, **kwargs: object) -> FastAPI:
    app = FastAPI()
    router = create_shared_router(state, **kwargs)
    app.include_router(router)
    return app


class TestBuildTopicInfoCallback:
    """The build_topic_info callback overrides topic listing."""

    def test_default_uses_topic_mgr(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        topic = MagicMock()
        topic.name = "my-topic"
        topic.document_count = 3
        topic.formatted_size = "1.2 MB"
        topic.project_id = "proj-1"
        state.topic_mgr.list_topics.return_value = [topic]

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-topic"
        assert data[0]["document_count"] == 3

    def test_custom_callback_overrides_listing(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)

        def custom_topics(s: object) -> list[TopicInfo]:
            return [
                TopicInfo(name="custom", document_count=7, size="2 MB", project_id="p1")
            ]

        app = _make_app(state, build_topic_info=custom_topics)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "custom"
        assert data[0]["document_count"] == 7


class TestGetSessionCallback:
    """The get_session callback controls which session is used for history."""

    def test_default_uses_per_project_session(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        project_dir = tmp_path / "proj-1"
        project_dir.mkdir()
        state.topic_mgr._storage._project_path.return_value = project_dir

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/history")
        assert resp.status_code == 200
        assert resp.json()["exchanges"] == []

    def test_custom_session_callback(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"

        # Create a global session with an exchange
        global_session = WebConversationSession(tmp_path)
        global_session.add_exchange(
            question="hi",
            answer="hello",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def custom_session(s: object, topic_name: str) -> WebConversationSession:
            return global_session

        app = _make_app(state, get_session=custom_session)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/history")
        assert resp.status_code == 200
        assert len(resp.json()["exchanges"]) == 1
        assert resp.json()["exchanges"][0]["question"] == "hi"


class TestResolveProjectIdsCallback:
    """The resolve_project_ids callback controls trace aggregation."""

    def test_default_uses_resolve_all(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve_all = MagicMock(return_value=["p1", "p2"])
        state.topic_mgr._storage.list_traces.return_value = []

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        state.topic_mgr.resolve_all.assert_called_once_with("my-topic")

    def test_custom_callback_overrides_resolution(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = []

        def custom_resolve(s: object, name: str) -> list[str]:
            return ["custom-proj"]

        app = _make_app(state, resolve_project_ids=custom_resolve)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/traces")
        assert resp.status_code == 200
        state.topic_mgr._storage.list_traces.assert_called_once_with("custom-proj")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/experimental/shared/test_shared_routes.py -v`
Expected: FAIL — tests reference callback parameters that don't exist yet.

**Step 3: Implement callback parameters in `create_shared_router()`**

Modify `src/shesha/experimental/shared/routes.py`:

1. Add `Callable` import and type aliases at top.
2. Change `create_shared_router()` signature to accept three optional callbacks.
3. In `list_topics()`: if `build_topic_info` is provided, call it; otherwise use existing logic. Change `t.paper_count` to `t.document_count` in the default.
4. In history/export/context-budget routes: if `get_session` is provided, call it to get the session; otherwise use existing per-project logic.
5. In trace routes: if `resolve_project_ids` is provided, call it; otherwise use existing `_resolve_all_project_ids()`.
6. Export `_parse_trace_file` and `_resolve_topic_or_404` (add to module `__all__` or just leave as public — they're imported by tools).

The key changes to the function signature:

```python
from collections.abc import Callable

# Type aliases for callbacks
GetSession = Callable[[object, str], WebConversationSession]
BuildTopicInfo = Callable[[object], list[TopicInfo]]
ResolveProjectIds = Callable[[object, str], list[str]]


def create_shared_router(
    state: Any,
    *,
    get_session: GetSession | None = None,
    build_topic_info: BuildTopicInfo | None = None,
    resolve_project_ids: ResolveProjectIds | None = None,
    include_topic_crud: bool = True,
    include_per_topic_history: bool = True,
    include_context_budget: bool = True,
) -> APIRouter:
```

Wrap topic CRUD registration in `if include_topic_crud:` (same pattern as
`include_per_topic_history`). Inside `list_topics()`:
```python
if include_topic_crud:
    @router.get("/api/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        if build_topic_info is not None:
            return build_topic_info(state)
        topics = state.topic_mgr.list_topics()
        return [
            TopicInfo(
                name=t.name,
                document_count=t.document_count,
                size=t.formatted_size,
                project_id=t.project_id,
            )
            for t in topics
        ]
    # ... also create_topic, rename_topic, delete_topic inside the same block
```

For history/export/context-budget — extract session resolution into a helper:
```python
def _get_session_for_topic(topic_name: str) -> WebConversationSession:
    if get_session is not None:
        return get_session(state, topic_name)
    project_id = _resolve_topic_or_404(state, topic_name)
    project_dir = state.topic_mgr._storage._project_path(project_id)
    return WebConversationSession(project_dir)
```

For traces — use the callback or default:
```python
def _get_project_ids(name: str) -> list[str]:
    if resolve_project_ids is not None:
        return resolve_project_ids(state, name)
    return _resolve_all_project_ids(state, name)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/experimental/shared/test_shared_routes.py -v`
Expected: All PASS.

**Step 5: Run full test suite**

Run: `make all`
Expected: All pass (existing tools don't use shared router yet, so no breakage).

**Step 6: Commit**

```bash
git add src/shesha/experimental/shared/routes.py tests/experimental/shared/test_shared_routes.py
git commit -m "feat: add callback parameters to create_shared_router()"
```

---

### Task 2: Standardize arxiv schemas on generic field names

Remove the arxiv-specific `TopicInfo` override (uses `paper_count`) and `ExchangeSchema` override (uses `paper_ids`). Both tools use the shared generic schemas with `document_count` and `document_ids`.

**Files:**
- Modify: `src/shesha/experimental/web/schemas.py`
- Modify: `src/shesha/experimental/web/api.py` (topic listing uses `paper_count` → `document_count`)
- Test: `tests/experimental/web/test_schemas_standardized.py` (create)

**Step 1: Write failing test**

Create `tests/experimental/web/test_schemas_standardized.py`:

```python
"""Verify arxiv schemas use standardized field names."""

from shesha.experimental.shared.schemas import ExchangeSchema, TopicInfo


def test_topic_info_uses_document_count() -> None:
    """TopicInfo from shared schemas has document_count, not paper_count."""
    info = TopicInfo(name="test", document_count=5, size="1 MB", project_id="p1")
    assert info.document_count == 5
    assert not hasattr(info, "paper_count")


def test_exchange_schema_uses_document_ids() -> None:
    """ExchangeSchema from shared schemas has document_ids, not paper_ids."""
    ex = ExchangeSchema(
        exchange_id="e1",
        question="q",
        answer="a",
        timestamp="2026-01-01",
        tokens={"prompt": 1, "completion": 1, "total": 2},
        execution_time=0.5,
        model="test",
        document_ids=["d1"],
    )
    assert ex.document_ids == ["d1"]
    assert not hasattr(ex, "paper_ids")


def test_web_schemas_reexport_shared_topic_info() -> None:
    """web.schemas.TopicInfo should be the shared version (document_count)."""
    from shesha.experimental.web.schemas import TopicInfo as WebTopicInfo

    info = WebTopicInfo(name="test", document_count=5, size="1 MB", project_id="p1")
    assert info.document_count == 5


def test_web_schemas_reexport_shared_exchange() -> None:
    """web.schemas.ExchangeSchema should be the shared version (document_ids)."""
    from shesha.experimental.web.schemas import ExchangeSchema as WebExchange

    ex = WebExchange(
        exchange_id="e1",
        question="q",
        answer="a",
        timestamp="2026-01-01",
        tokens={"prompt": 1, "completion": 1, "total": 2},
        execution_time=0.5,
        model="test",
        document_ids=["d1"],
    )
    assert ex.document_ids == ["d1"]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/experimental/web/test_schemas_standardized.py -v`
Expected: The `test_web_schemas_reexport_*` tests FAIL because `web.schemas` still defines local overrides.

**Step 3: Update `web/schemas.py`**

Remove the local `TopicInfo`, `ExchangeSchema`, and `ConversationHistory` overrides. Add re-exports of shared versions instead:

```python
"""Pydantic schemas for the arxiv web API.

Generic schemas are imported from shesha.experimental.shared.schemas and
re-exported here.  Arxiv-specific schemas (PaperAdd, PaperInfo, SearchResult,
DownloadTaskStatus) are defined locally.
"""

from __future__ import annotations

from pydantic import BaseModel

# Re-export all shared schemas.
from shesha.experimental.shared.schemas import (
    ContextBudget,
    ConversationHistory,
    ExchangeSchema,
    ModelInfo,
    ModelUpdate,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)

__all__ = [
    "ContextBudget",
    "ConversationHistory",
    "DownloadTaskStatus",
    "ExchangeSchema",
    "ModelInfo",
    "ModelUpdate",
    "PaperAdd",
    "PaperInfo",
    "SearchResult",
    "TopicCreate",
    "TopicInfo",
    "TopicRename",
    "TraceFull",
    "TraceListItem",
    "TraceStepSchema",
]


# Arxiv-only schemas

class PaperAdd(BaseModel):
    arxiv_id: str
    topics: list[str]


class PaperInfo(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    source_type: str | None = None


class SearchResult(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    in_topics: list[str] = []


class DownloadTaskStatus(BaseModel):
    task_id: str
    papers: list[dict[str, str]]
```

**Step 4: Update `web/api.py` topic listing**

In `_create_arxiv_router()`, the `list_topics()` route currently reads `t.paper_count`. Change to `t.document_count`:

```python
@router.get("/api/topics", response_model=list[TopicInfo])
def list_topics() -> list[TopicInfo]:
    topics = state.topic_mgr.list_topics()
    return [
        TopicInfo(
            name=t.name,
            document_count=t.paper_count,
            size=t.formatted_size,
            project_id=t.project_id,
        )
        for t in topics
    ]
```

Note: The topic manager's internal attribute is still called `paper_count` (it's an arXiv concept on the data model). The API response field is now `document_count`.

**Step 5: Run tests**

Run: `pytest tests/experimental/web/test_schemas_standardized.py -v`
Expected: All PASS.

Run: `make all`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/shesha/experimental/web/schemas.py src/shesha/experimental/web/api.py tests/experimental/web/test_schemas_standardized.py
git commit -m "refactor: standardize arxiv schemas on generic field names"
```

---

### Task 3: Wire code-explorer to use `create_shared_router()`

Delete duplicated routes from code-explorer's `api.py` and use the shared router with callbacks instead.

**Files:**
- Modify: `src/shesha/experimental/code_explorer/api.py`
- Modify: `tests/experimental/shared/test_shared_routes.py` (add code-explorer-specific integration test)

**Step 1: Write failing integration test**

Add to `tests/experimental/shared/test_shared_routes.py`:

```python
class TestCodeExplorerCallbacks:
    """Code explorer uses global session and custom topic listing."""

    def test_global_session_used_for_history(self, tmp_path: Path) -> None:
        """Code explorer history routes use global session, not per-project."""
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"

        global_session = WebConversationSession(tmp_path)
        global_session.add_exchange(
            question="global q",
            answer="global a",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def get_global_session(s: object, topic_name: str) -> WebConversationSession:
            return global_session

        app = _make_app(state, get_session=get_global_session)
        client = TestClient(app)

        # History for any topic returns global session data
        resp = client.get("/api/topics/any-topic/history")
        assert resp.status_code == 200
        assert len(resp.json()["exchanges"]) == 1
        assert resp.json()["exchanges"][0]["question"] == "global q"

    def test_custom_topic_listing(self, tmp_path: Path) -> None:
        """Code explorer builds TopicInfo from plain topic names + repo counts."""
        state = _make_state(tmp_path)

        def build_code_topics(s: object) -> list[TopicInfo]:
            return [
                TopicInfo(name="my-topic", document_count=2, size="", project_id="topic:my-topic")
            ]

        app = _make_app(state, build_topic_info=build_code_topics)
        client = TestClient(app)
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["document_count"] == 2
        assert data[0]["project_id"] == "topic:my-topic"
```

**Step 2: Run test to verify it passes** (these test the shared router which we already implemented)

Run: `pytest tests/experimental/shared/test_shared_routes.py::TestCodeExplorerCallbacks -v`
Expected: PASS (callbacks already work from Task 1).

**Step 3: Refactor code-explorer `api.py`**

In `src/shesha/experimental/code_explorer/api.py`:

1. Import `create_shared_router` and `_parse_trace_file` from shared routes.
2. Delete the local `_parse_trace_file()` function.
3. Delete all these route groups from `_create_repo_router()`:
   - Per-topic history routes (lines 261-275)
   - Trace routes (lines 281-350)
   - Model routes (lines 356-375)
   - Context budget route (lines 381-409)
4. In `create_api()`, create the shared router with callbacks and pass it as an extra router alongside the repo router.

The callbacks for code-explorer:

```python
def _build_code_topic_info(state: CodeExplorerState) -> list[TopicInfo]:
    names = state.topic_mgr.list_topics()
    return [
        TopicInfo(
            name=n,
            document_count=len(state.topic_mgr.list_repos(n)),
            size="",
            project_id=f"topic:{n}",
        )
        for n in names
    ]


def _get_global_session(
    state: CodeExplorerState, topic_name: str
) -> WebConversationSession:
    return state.session


def _resolve_code_project_ids(
    state: CodeExplorerState, topic_name: str
) -> list[str]:
    try:
        repos = state.topic_mgr.list_repos(topic_name)
        if repos:
            return repos
    except ValueError:
        pass
    return state.shesha.list_projects()
```

In `create_api()`:

```python
def create_api(state: CodeExplorerState) -> FastAPI:
    repo_router = _create_repo_router(state)
    shared_router = create_shared_router(
        state,
        get_session=lambda s, name: _get_global_session(state, name),
        resolve_project_ids=lambda s, name: _resolve_code_project_ids(state, name),
        include_topic_crud=False,
        include_per_topic_history=False,
        include_context_budget=True,
    )
    # ... create_app with extra_routers=[repo_router, shared_router]
```

Note: `include_topic_crud=False` because the code-explorer topic manager has
a different interface (no `resolve()`, uses `create()` idempotently).
`include_per_topic_history=False` because code-explorer's per-topic history
routes delegate to the global session and are already on the repo router.
The global history routes (`/api/history`, `/api/export`) also stay in the
repo router. The shared router provides: traces, model, and context budget.

**Step 4: Run full test suite**

Run: `make all`
Expected: All pass. Existing code-explorer tests should still work because the routes still exist at the same paths.

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py tests/experimental/shared/test_shared_routes.py
git commit -m "refactor: wire code-explorer to use create_shared_router()"
```

---

### Task 4: Wire arxiv-explorer to use `create_shared_router()`

Delete duplicated routes from arxiv's `api.py` and use the shared router with callbacks.

**Files:**
- Modify: `src/shesha/experimental/web/api.py`

**Step 1: Write failing test**

Add to `tests/experimental/shared/test_shared_routes.py`:

```python
class TestArxivCallbacks:
    """Arxiv uses per-project session with legacy filename."""

    def test_per_project_session_with_legacy_filename(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        project_dir = tmp_path / "proj-1"
        project_dir.mkdir()
        state.topic_mgr._storage._project_path.return_value = project_dir

        from shesha.experimental.web.session import WebConversationSession as ArxivSession

        session = ArxivSession(project_dir)
        session.add_exchange(
            question="arxiv q",
            answer="arxiv a",
            trace_id=None,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            execution_time=0.1,
            model="test",
        )

        def get_arxiv_session(s: object, topic_name: str) -> WebConversationSession:
            pid = state.topic_mgr.resolve(topic_name)
            pdir = state.topic_mgr._storage._project_path(pid)
            return ArxivSession(pdir)

        app = _make_app(state, get_session=get_arxiv_session)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/history")
        assert resp.status_code == 200
        assert len(resp.json()["exchanges"]) == 1
        assert resp.json()["exchanges"][0]["question"] == "arxiv q"
```

**Step 2: Run test**

Run: `pytest tests/experimental/shared/test_shared_routes.py::TestArxivCallbacks -v`
Expected: PASS (callbacks already work).

**Step 3: Refactor arxiv `api.py`**

In `src/shesha/experimental/web/api.py`:

1. Import `create_shared_router` from shared routes.
2. Delete the local `_parse_trace_file()` function.
3. Delete the local `_resolve_topic_or_404()` function (import from shared if still needed by paper routes).
4. Delete from `_create_arxiv_router()`:
   - Trace routes (lines 286-354)
   - History/export routes (lines 358-379)
   - Model routes (lines 383-402)
   - Context budget route (lines 406-447)
   - Topic CRUD routes (lines 87-122) — these can now use the shared router since we standardized field names
5. Keep in `_create_arxiv_router()`:
   - Paper routes (list, add, remove, task status)
   - Search routes (arxiv API search, local search)
6. In `create_api()`, create shared router with arxiv callbacks and include alongside the arxiv-specific router.

The callbacks for arxiv:

```python
def _build_arxiv_topic_info(state: AppState) -> list[TopicInfo]:
    topics = state.topic_mgr.list_topics()
    return [
        TopicInfo(
            name=t.name,
            document_count=t.paper_count,
            size=t.formatted_size,
            project_id=t.project_id,
        )
        for t in topics
    ]


def _get_arxiv_session(state: AppState, topic_name: str) -> ArxivSession:
    project_id = _resolve_topic_or_404(state, topic_name)
    project_dir = state.topic_mgr._storage._project_path(project_id)
    return ArxivSession(project_dir)
```

Note: `_resolve_topic_or_404` is still needed for paper routes — import it from `shesha.experimental.shared.routes`.

**Step 4: Run full test suite**

Run: `make all`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/api.py tests/experimental/shared/test_shared_routes.py
git commit -m "refactor: wire arxiv-explorer to use create_shared_router()"
```

---

### Task 5: Move connection-loss banner into `AppShell`

Both `App.tsx` files render an identical connection-loss banner. Move it into the shared `AppShell` component.

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/AppShell.tsx`
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/AppShell.test.tsx`

**Step 1: Write failing test**

Add to `src/shesha/experimental/shared/frontend/src/components/__tests__/AppShell.test.tsx`:

```typescript
it('shows connection lost banner when connected is false', () => {
  render(<AppShell connected={false}>Content</AppShell>)
  expect(screen.getByText(/Connection lost/)).toBeTruthy()
})

it('hides connection lost banner when connected is true', () => {
  render(<AppShell connected={true}>Content</AppShell>)
  expect(screen.queryByText(/Connection lost/)).toBeNull()
})

it('hides connection lost banner by default', () => {
  render(<AppShell>Content</AppShell>)
  expect(screen.queryByText(/Connection lost/)).toBeNull()
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/AppShell.test.tsx`
Expected: FAIL — AppShell doesn't accept `connected` prop.

**Step 3: Add `connected` prop to AppShell**

```typescript
import type { ReactNode } from 'react'

interface AppShellProps {
  children: ReactNode
  connected?: boolean
}

export default function AppShell({ children, connected }: AppShellProps) {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface-0 text-text-primary font-sans">
      {connected === false && (
        <div className="bg-amber/10 border-b border-amber text-amber text-sm px-4 py-1.5 text-center">
          Connection lost. Reconnecting...
        </div>
      )}
      {children}
    </div>
  )
}
```

**Step 4: Run test to verify it passes**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/AppShell.test.tsx`
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/AppShell.tsx src/shesha/experimental/shared/frontend/src/components/__tests__/AppShell.test.tsx
git commit -m "feat: add connected prop to AppShell for connection-loss banner"
```

---

### Task 6: Extract `useAppState` hook into shared-ui

Extract common state management and handlers from both `App.tsx` files into a reusable hook.

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/hooks/useAppState.ts`
- Create: `src/shesha/experimental/shared/frontend/src/hooks/__tests__/useAppState.test.ts`
- Modify: `src/shesha/experimental/shared/frontend/src/index.ts` (add export)

**Step 1: Write failing test**

Create `src/shesha/experimental/shared/frontend/src/hooks/__tests__/useAppState.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the hooks that useAppState depends on
const mockSend = vi.fn()
const mockOnMessage = vi.fn()
const mockToggleTheme = vi.fn()

vi.mock('../useWebSocket', () => ({
  useWebSocket: () => ({
    connected: true,
    send: mockSend,
    onMessage: mockOnMessage,
  }),
}))

vi.mock('../useTheme', () => ({
  useTheme: () => ({
    dark: true,
    toggle: mockToggleTheme,
  }),
}))

// Mock fetch for model loading
vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ model: 'test-model', max_input_tokens: 128000 }),
}))

import { useAppState } from '../useAppState'

describe('useAppState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // onMessage returns an unsubscribe function
    mockOnMessage.mockReturnValue(() => {})
  })

  it('provides initial state', () => {
    const { result } = renderHook(() => useAppState())
    expect(result.current.dark).toBe(true)
    expect(result.current.connected).toBe(true)
    expect(result.current.phase).toBe('Ready')
    expect(result.current.activeTopic).toBeNull()
    expect(result.current.sidebarWidth).toBe(224)
    expect(result.current.traceView).toBeNull()
    expect(result.current.historyVersion).toBe(0)
  })

  it('registers WebSocket message listener', () => {
    renderHook(() => useAppState())
    expect(mockOnMessage).toHaveBeenCalledWith(expect.any(Function))
  })

  it('updates phase on status message', () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = renderHook(() => useAppState())
    act(() => {
      messageHandler({ type: 'status', phase: 'Querying' })
    })
    expect(result.current.phase).toBe('Querying')
  })

  it('resets phase on complete message', () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = renderHook(() => useAppState())
    act(() => {
      messageHandler({
        type: 'complete',
        answer: 'done',
        trace_id: 't1',
        tokens: { prompt: 10, completion: 5, total: 15 },
        duration_ms: 100,
      })
    })
    expect(result.current.phase).toBe('Ready')
    expect(result.current.tokens).toEqual({ prompt: 10, completion: 5, total: 15 })
  })

  it('calls onComplete callback after complete message', () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const onComplete = vi.fn()
    renderHook(() => useAppState({ onComplete }))
    act(() => {
      messageHandler({
        type: 'complete',
        answer: 'done',
        trace_id: null,
        tokens: { prompt: 1, completion: 1, total: 2 },
        duration_ms: 50,
      })
    })
    expect(onComplete).toHaveBeenCalled()
  })

  it('forwards unknown messages to onExtraMessage', () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const onExtraMessage = vi.fn()
    renderHook(() => useAppState({ onExtraMessage }))
    act(() => {
      messageHandler({ type: 'citation_progress', current: 1, total: 3 })
    })
    expect(onExtraMessage).toHaveBeenCalledWith({ type: 'citation_progress', current: 1, total: 3 })
  })

  it('handleSidebarDrag creates mouse listeners', () => {
    const addListener = vi.spyOn(document, 'addEventListener')
    const { result } = renderHook(() => useAppState())
    act(() => {
      result.current.handleSidebarDrag({
        preventDefault: vi.fn(),
        clientX: 100,
      } as any)
    })
    expect(addListener).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(addListener).toHaveBeenCalledWith('mouseup', expect.any(Function))
    addListener.mockRestore()
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/hooks/__tests__/useAppState.test.ts`
Expected: FAIL — module doesn't exist.

**Step 3: Implement `useAppState` hook**

Create `src/shesha/experimental/shared/frontend/src/hooks/useAppState.ts`:

```typescript
import { useState, useCallback, useEffect, useRef, type MouseEvent } from 'react'
import { useTheme } from './useTheme'
import { useWebSocket } from './useWebSocket'
import { sharedApi } from '../api/client'
import type { ContextBudget, WSMessage } from '../types'

export interface AppStateOptions {
  onComplete?: () => void
  onExtraMessage?: (msg: any) => void
}

export function useAppState(options?: AppStateOptions) {
  const { dark, toggle: toggleTheme } = useTheme()
  const { connected, send, onMessage } = useWebSocket<WSMessage>()

  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [modelName, setModelName] = useState('\u2014')
  const [tokens, setTokens] = useState({ prompt: 0, completion: 0, total: 0 })
  const [budget, setBudget] = useState<ContextBudget | null>(null)
  const [phase, setPhase] = useState('Ready')
  const [documentBytes, setDocumentBytes] = useState(0)
  const [sidebarWidth, setSidebarWidth] = useState(224)
  const [historyVersion, setHistoryVersion] = useState(0)
  const [traceView, setTraceView] = useState<{ topic: string; traceId: string } | null>(null)

  const dragging = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options

  // Load model name on mount
  useEffect(() => {
    sharedApi.model.get().then(info => setModelName(info.model)).catch(() => {
      // Model API may not be available yet
    })
  }, [])

  // WebSocket message handler
  useEffect(() => {
    return onMessage((msg: any) => {
      if (msg.type === 'status') {
        setPhase(msg.phase)
      } else if (msg.type === 'step') {
        setPhase(`${msg.step_type} (iter ${msg.iteration})`)
        if (msg.prompt_tokens !== undefined) {
          setTokens({
            prompt: msg.prompt_tokens,
            completion: msg.completion_tokens ?? 0,
            total: msg.prompt_tokens + (msg.completion_tokens ?? 0),
          })
        }
      } else if (msg.type === 'complete') {
        setPhase('Ready')
        setTokens(msg.tokens)
        if (msg.document_bytes != null) setDocumentBytes(msg.document_bytes)
        optionsRef.current?.onComplete?.()
      } else if (msg.type === 'error') {
        // Only set phase to Error if onExtraMessage doesn't handle it
        if (optionsRef.current?.onExtraMessage) {
          optionsRef.current.onExtraMessage(msg)
        } else {
          setPhase('Error')
        }
      } else if (msg.type === 'cancelled') {
        setPhase('Ready')
      } else {
        optionsRef.current?.onExtraMessage?.(msg)
      }
    })
  }, [onMessage])

  const handleTopicSelect = useCallback((name: string) => {
    setActiveTopic(name)
    if (name) {
      sharedApi.contextBudget(name).then(setBudget).catch(() => {
        // Context budget may not be available for this topic
      })
    }
  }, [])

  const handleViewTrace = useCallback((traceId: string) => {
    setTraceView(prev => {
      const topic = prev?.topic ?? ''
      return { topic, traceId }
    })
  }, [])

  const handleSidebarDrag = useCallback((e: MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX
    const startWidth = sidebarWidth
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!dragging.current) return
      const newWidth = Math.min(600, Math.max(160, startWidth + ev.clientX - startX))
      setSidebarWidth(newWidth)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarWidth])

  return {
    // Theme
    dark, toggleTheme,
    // Connection
    connected, send, onMessage,
    // Status
    modelName, tokens, budget, setBudget, phase, setPhase, documentBytes,
    // Layout
    sidebarWidth, handleSidebarDrag,
    // Navigation
    activeTopic, setActiveTopic, handleTopicSelect,
    traceView, setTraceView, handleViewTrace,
    // History
    historyVersion, setHistoryVersion,
    // Tokens
    setTokens,
  }
}
```

**Step 4: Export from index.ts**

Add to `src/shesha/experimental/shared/frontend/src/index.ts`:

```typescript
export { useAppState } from './hooks/useAppState'
export type { AppStateOptions } from './hooks/useAppState'
```

**Step 5: Run test to verify it passes**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/hooks/__tests__/useAppState.test.ts`
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/hooks/useAppState.ts src/shesha/experimental/shared/frontend/src/hooks/__tests__/useAppState.test.ts src/shesha/experimental/shared/frontend/src/index.ts
git commit -m "feat: extract useAppState hook into shared-ui"
```

---

### Task 7: Refactor code-explorer `App.tsx` to use `useAppState`

Replace duplicated state/handlers with the shared hook.

**Files:**
- Modify: `src/shesha/experimental/code_explorer/frontend/src/App.tsx`
- Modify: `src/shesha/experimental/code_explorer/frontend/src/__tests__/App.test.tsx`

**Step 1: Update App.test.tsx mock to include useAppState**

The existing test mocks `@shesha/shared-ui`. Update the mock to also provide `useAppState`. Read the existing test, adjust the shared-ui mock to include:

```typescript
useAppState: () => ({
  dark: true, toggleTheme: vi.fn(),
  connected: true, send: vi.fn(), onMessage: vi.fn().mockReturnValue(() => {}),
  modelName: 'test-model',
  tokens: { prompt: 0, completion: 0, total: 0 },
  budget: null, setBudget: vi.fn(),
  phase: 'Ready', setPhase: vi.fn(),
  documentBytes: 0,
  sidebarWidth: 224, handleSidebarDrag: vi.fn(),
  activeTopic: null, setActiveTopic: vi.fn(), handleTopicSelect: vi.fn(),
  traceView: null, setTraceView: vi.fn(), handleViewTrace: vi.fn(),
  historyVersion: 0, setHistoryVersion: vi.fn(),
  setTokens: vi.fn(),
}),
```

**Step 2: Refactor `App.tsx`**

Replace all shared state declarations and handlers with:

```typescript
import { AppShell, TopicSidebar, ChatArea, StatusBar, TraceViewer, ToastContainer, showToast, useAppState } from '@shesha/shared-ui'
```

Then:
```typescript
const app = useAppState()
const {
  dark, toggleTheme, connected, send, onMessage,
  modelName, tokens, budget, phase, documentBytes,
  sidebarWidth, handleSidebarDrag,
  activeTopic, handleTopicSelect,
  traceView, setTraceView, handleViewTrace,
  historyVersion, setHistoryVersion, setTokens,
} = app
```

Delete:
- `useTheme()` call (now inside `useAppState`)
- `useWebSocket()` call (now inside `useAppState`)
- Local state for: `modelName`, `tokens`, `budget`, `phase`, `documentBytes`, `sidebarWidth`, `historyVersion`, `traceView`, `dragging` ref
- `useEffect` for model loading
- `useEffect` for WebSocket message listener
- `handleSidebarDrag` callback
- `handleViewTrace` callback

Keep (domain-specific):
- `selectedRepos`, `viewingRepo`, `viewingAnalysis`, `showAddRepo`, `topicNames`, `allRepos`, `uncategorizedRepos`, `reposVersion` state
- All repo handlers
- `loadDocuments`, `handleLoadTopics`, `handleDocsLoaded`, `handleViewRepo`
- `loadHistory`, `handleClearHistory`, `handleExport` (code-explorer export is global, not per-topic)

Pass `connected` to `AppShell`:
```tsx
<AppShell connected={connected}>
```

Remove the manual connection-loss banner `<div>`.

**Step 3: Run tests**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All PASS.

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/App.tsx src/shesha/experimental/code_explorer/frontend/src/__tests__/App.test.tsx
git commit -m "refactor: code-explorer App.tsx uses useAppState hook"
```

---

### Task 8: Refactor arxiv-explorer `App.tsx` to use `useAppState`

Replace duplicated state/handlers with the shared hook, keeping citation and paper-specific logic.

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx`

**Step 1: Refactor `App.tsx`**

Import `useAppState` from `@shesha/shared-ui`. Use `onComplete` and `onExtraMessage` callbacks:

```typescript
const app = useAppState({
  onComplete: () => {
    if (activeTopic) {
      api.contextBudget(activeTopic).then(app.setBudget).catch(() => {})
    }
  },
  onExtraMessage: (msg: any) => {
    if (msg.type === 'error') {
      const errorMsg = msg.message ?? 'Unknown error'
      if (citationCheckingRef.current) {
        setCitationChecking(false)
        setCitationError(errorMsg)
      } else {
        app.setPhase('Error')
        showToast(errorMsg, 'error')
      }
    } else if (msg.type === 'citation_progress') {
      setCitationProgress({ current: msg.current, total: msg.total, phase: msg.phase })
    } else if (msg.type === 'citation_report') {
      setCitationChecking(false)
      setCitationReport(msg.papers)
    }
  },
})
```

Delete:
- `useTheme()` and `useWebSocket()` calls
- Local state for: `modelName`, `tokens`, `budget`, `phase`, `documentBytes`, `sidebarWidth`, `dragging` ref
- `useEffect` for model loading
- `useEffect` for WebSocket message listener (replaced by `onExtraMessage`)
- `handleSidebarDrag` callback
- `handleViewTrace` callback

Keep (domain-specific):
- `selectedPapers`, `viewingPaper`, `topicPapersList` state
- Citation state and handlers
- Search/help panel state
- Download task state
- All paper handlers

Pass `connected` to `AppShell`. Remove manual connection-loss banner.

**Step 2: Run tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS.

**Step 3: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/App.tsx
git commit -m "refactor: arxiv-explorer App.tsx uses useAppState hook"
```

---

### Task 9: Update arxiv frontend types, API client, components, and WebSocket adapter

Now that the backend returns `document_count` instead of `paper_count` and
`document_ids` instead of `paper_ids`, update ALL frontend files that reference
the old field names, and simplify the backend `_PaperIdAdapter`.

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/types/index.ts`
- Modify: `src/shesha/experimental/web/frontend/src/api/client.ts`
- Modify: `src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/ChatArea.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx` (verify `check_citations` messages)
- Modify: `src/shesha/experimental/web/frontend/src/components/__tests__/TopicSidebar.test.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/__tests__/ChatMessage.test.tsx`
- Modify: `src/shesha/experimental/web/websockets.py` (simplify `_PaperIdAdapter`)

**Step 1: Update types**

Remove the `TopicInfo` override that uses `paper_count`. Use the shared
`TopicInfo` directly. Remove the `Exchange` override that uses `paper_ids`.
Use the shared `Exchange` directly. Keep arxiv-specific `WSMessage` extension
for citation messages only (the `complete` message no longer needs `paper_ids`
— it uses shared `document_ids`).

```typescript
// Re-export shared types directly — no more overrides
export type { TopicInfo, Exchange, TraceStep, TraceListItem, TraceFull, ContextBudget, ModelInfo } from '@shesha/shared-ui'
```

**Step 2: Update API client**

Remove the `topics.list` override (shared `TopicInfo` with `document_count`
now matches). Remove the `history.get` override (shared `Exchange` with
`document_ids` now matches).

```typescript
export const api = {
  ...sharedApi,
  // Arxiv-specific endpoints only
  papers: { ... },
  search: ...,
}
```

**Step 3: Update TopicSidebar wrapper**

Change `paper_count` references to `document_count`. The UI can still display
"N papers" — the field name is internal.

**Step 4: Update ChatArea and ChatMessage**

Change all `paper_ids` references to `document_ids` in:
- `components/ChatArea.tsx` — `ex.paper_ids` → `ex.document_ids`,
  `msg.paper_ids` → `msg.document_ids`, update comments
- `components/ChatMessage.tsx` — `exchange.paper_ids` → `exchange.document_ids`

**Step 5: Verify App.tsx `check_citations` messages**

The `check_citations` WebSocket messages in `App.tsx` send `paper_ids` as a
**domain-specific field** for citation checking (not the same concept as
`document_ids` for query documents). These MUST stay as `paper_ids` — they
are arxiv-specific and are not subject to the generic field name
standardization.

**Step 6: Update test files**

- `components/__tests__/TopicSidebar.test.tsx` — `paper_count` → `document_count`
- `components/__tests__/ChatMessage.test.tsx` — `paper_ids` → `document_ids`

**Step 7: Simplify `_PaperIdAdapter` in `web/websockets.py`**

The `_PaperIdAdapter` previously translated `paper_ids` ↔ `document_ids`
on query messages. Now that both frontend and backend use `document_ids`
natively for queries, the adapter no longer needs to translate query messages.

Remove the `_PaperIdAdapter` class entirely. The `check_citations` message
already uses `paper_ids` natively (domain-specific) and bypasses the adapter's
translation logic, so removing the adapter has no effect on citation checking.

Update `websocket_handler()` in `web/websockets.py` to pass the raw
WebSocket directly to the shared handler instead of wrapping it in the adapter.

**Step 8: Run tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS.

Run: `pytest tests/experimental/web/ -v`
Expected: All PASS.

**Step 9: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/ src/shesha/experimental/web/websockets.py
git commit -m "refactor: arxiv frontend and WS adapter use standardized field names"
```

---

### Task 10: Update `docs/extending-web-tools.md`

Update the guide to reflect the new shared infrastructure.

**Files:**
- Modify: `docs/extending-web-tools.md`

**Step 1: Read the current guide and update**

Key changes:
- Section 3 (Backend): Document `create_shared_router()` callback parameters with examples for customizing session, topic listing, and project ID resolution
- Section 3 (Shared routes): Show how to use `create_shared_router()` with `build_topic_info`, `get_session`, `resolve_project_ids` instead of reimplementing routes
- Section 4 (Frontend): Document the `useAppState` hook with `onComplete` and `onExtraMessage` options
- Section 4 (Frontend): Document `AppShell`'s `connected` prop for connection-loss banner
- Remove examples that show manual route implementation for traces/model/budget/history
- Verify all file paths and code examples still match the codebase

**Step 2: Commit**

```bash
git add docs/extending-web-tools.md
git commit -m "docs: update extending-web-tools guide for shared code consolidation"
```

---

### Task 11: Final verification

Run all tests across the entire project.

**Step 1: Backend**

Run: `make all`
Expected: All pass (format + lint + typecheck + test).

**Step 2: Shared frontend**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run`
Expected: All pass.

**Step 3: Code-explorer frontend**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All pass.

**Step 4: Arxiv frontend**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All pass.

**Step 5: Commit any remaining fixes, then use the finishing-a-development-branch skill**
