# Code Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a web-based git repository explorer and extract shared web infrastructure from the arxiv explorer.

**Architecture:** Shared-first extraction — move generic backend (FastAPI routes, WebSocket handler, session) and frontend (React components, hooks) from `web/` into `shared/`, then build `code_explorer/` on top. Repos are global singletons; topics hold references. Two-column layout with inline repo detail and on-demand trace viewer.

**Tech Stack:** Python 3.12, FastAPI, WebSockets, React 19, Vite, Tailwind CSS, Vitest, pytest

**Design doc:** `docs/plans/2026-02-13-code-explorer-design.md`

**Reuse policy:** Before writing any code, check whether an existing implementation can be reused or adapted. When uncertain, ask.

---

## Phase 1: Shared Backend Module

### Task 1: Create shared module skeleton

**Files:**
- Create: `src/shesha/experimental/shared/__init__.py`

**Step 1: Create the module directory and __init__.py**

```python
# src/shesha/experimental/shared/__init__.py
"""Shared web infrastructure for Shesha experimental tools."""
```

**Step 2: Verify import works**

Run: `python -c "import shesha.experimental.shared"`
Expected: No error

**Step 3: Commit**

```bash
git add src/shesha/experimental/shared/__init__.py
git commit -m "feat: create shared experimental module skeleton"
```

---

### Task 2: Extract session.py to shared

The existing `web/session.py` is almost entirely generic. The only arxiv-specific detail is the `paper_ids` field name, which becomes `document_ids`.

**Files:**
- Create: `src/shesha/experimental/shared/session.py`
- Create: `tests/unit/experimental/shared/__init__.py`
- Create: `tests/unit/experimental/shared/test_session.py`
- Reference: `src/shesha/experimental/web/session.py` (existing, read first)
- Reference: `tests/unit/experimental/web/test_session.py` (existing, read first)

**Step 1: Read the existing session.py and its tests**

Read `src/shesha/experimental/web/session.py` and `tests/unit/experimental/web/test_session.py` to understand the current implementation.

**Step 2: Write the failing test for shared session**

Copy the existing `test_session.py` to the shared test directory. Rename all `paper_ids` references to `document_ids`. Update the import to `from shesha.experimental.shared.session import WebConversationSession`. The tests should fail because the shared module doesn't exist yet.

Run: `pytest tests/unit/experimental/shared/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create shared/session.py**

Copy `web/session.py` to `shared/session.py`. Rename `paper_ids` → `document_ids` in the `Exchange` dataclass and all references. Keep all other logic identical.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/shared/test_session.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/session.py \
        tests/unit/experimental/shared/__init__.py \
        tests/unit/experimental/shared/test_session.py
git commit -m "feat: extract generic session management to shared module"
```

---

### Task 3: Extract schemas.py to shared

Generic schemas: `TopicCreate`, `TopicRename`, `TopicInfo`, `TraceStepSchema`, `TraceListItem`, `TraceFull`, `ExchangeSchema`, `ConversationHistory`, `ModelInfo`, `ModelUpdate`, `ContextBudget`. Arxiv-specific schemas (`PaperAdd`, `PaperInfo`, `SearchResult`, `DownloadTaskStatus`) stay in `web/schemas.py`.

**Files:**
- Create: `src/shesha/experimental/shared/schemas.py`
- Create: `tests/unit/experimental/shared/test_schemas.py`
- Reference: `src/shesha/experimental/web/schemas.py` (read first)
- Reference: `tests/unit/experimental/web/test_schemas.py` (read first)

**Step 1: Read the existing schemas.py and its tests**

**Step 2: Write failing tests for shared schemas**

Write tests for all generic schema classes. Update imports to `from shesha.experimental.shared.schemas import ...`.

Run: `pytest tests/unit/experimental/shared/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create shared/schemas.py with generic models only**

Copy only the generic Pydantic models from `web/schemas.py`. Leave arxiv-specific models in `web/schemas.py`.

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/shared/test_schemas.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/schemas.py \
        tests/unit/experimental/shared/test_schemas.py
git commit -m "feat: extract generic Pydantic schemas to shared module"
```

---

### Task 4: Extract WebSocket handler to shared

The generic WebSocket handler handles `query` and `cancel` messages. Citation checking stays in `web/websockets.py`. The shared handler should be extensible — apps can register additional message handlers.

**Files:**
- Create: `src/shesha/experimental/shared/websockets.py`
- Create: `tests/unit/experimental/shared/test_ws.py`
- Reference: `src/shesha/experimental/web/websockets.py` (read first — lines 70-261 are generic)
- Reference: `tests/unit/experimental/web/test_ws.py` (read first)

**Step 1: Read existing websockets.py and test_ws.py**

Focus on `websocket_handler()` (lines 70-105) and `_handle_query()` (lines 107-261). Note: the query handler loads documents, builds history context, runs the RLM engine, and streams progress via WebSocket.

**Step 2: Write failing tests for shared WebSocket handler**

Adapt the generic query/cancel tests from `test_ws.py`. Import from `shesha.experimental.shared.websockets`.

Run: `pytest tests/unit/experimental/shared/test_ws.py -v`
Expected: FAIL

**Step 3: Implement shared WebSocket handler**

Extract the generic `websocket_handler()` and `_handle_query()`. The handler should accept a dictionary of additional message handlers so apps can extend it:

```python
async def websocket_handler(
    websocket: WebSocket,
    state: Any,
    extra_handlers: dict[str, Callable] | None = None,
) -> None:
```

The `_handle_query()` function needs to be parameterized for how it builds document context. Currently it has arxiv-specific citation instruction building. Make the context builder injectable:

```python
async def _handle_query(
    websocket: WebSocket,
    data: dict,
    state: Any,
    build_context: Callable | None = None,
) -> None:
```

Use `document_ids` instead of `paper_ids` in message handling.

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/shared/test_ws.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/websockets.py \
        tests/unit/experimental/shared/test_ws.py
git commit -m "feat: extract generic WebSocket query handler to shared module"
```

---

### Task 5: Extract app_factory.py to shared

Generic FastAPI app creation: lifespan hook, CORS, static file serving.

**Files:**
- Create: `src/shesha/experimental/shared/app_factory.py`
- Create: `tests/unit/experimental/shared/test_app_factory.py`
- Reference: `src/shesha/experimental/web/api.py` (lines 47-55 for app creation, lines 431-450 for static/ws mounting)

**Step 1: Read existing api.py app creation code**

**Step 2: Write failing test**

Test that `create_app()` returns a FastAPI instance with CORS middleware and static file mounting.

Run: `pytest tests/unit/experimental/shared/test_app_factory.py -v`
Expected: FAIL

**Step 3: Implement app_factory.py**

```python
def create_app(
    state: Any,
    title: str,
    static_dir: Path | None = None,
    ws_handler: Callable | None = None,
    extra_routers: list[APIRouter] | None = None,
) -> FastAPI:
```

The factory:
1. Creates FastAPI with lifespan that calls `state.shesha.start()` / `state.shesha.stop()`
2. Adds CORS middleware
3. Mounts WebSocket endpoint at `/api/ws`
4. Mounts static files from `static_dir` if provided
5. Includes any extra routers

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/shared/test_app_factory.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/app_factory.py \
        tests/unit/experimental/shared/test_app_factory.py
git commit -m "feat: extract FastAPI app factory to shared module"
```

---

### Task 6: Extract generic routes to shared

Topic CRUD, trace listing/retrieval, history/export, model management, context budget.

**Files:**
- Create: `src/shesha/experimental/shared/routes.py`
- Create: `tests/unit/experimental/shared/test_routes.py`
- Reference: `src/shesha/experimental/web/api.py` (lines 59-94 topics, 252-361 traces/history, 365-428 model/budget)
- Reference: `tests/unit/experimental/web/test_api_topics.py`, `test_api_traces.py`, `test_api_misc.py`

**Step 1: Read existing route code and tests**

**Step 2: Write failing tests for shared routes**

Adapt topic, trace, history, model, and context-budget tests. Import from shared. Use `document_ids` where the existing code uses `paper_ids`.

Run: `pytest tests/unit/experimental/shared/test_routes.py -v`
Expected: FAIL

**Step 3: Implement shared/routes.py**

Create a function that returns a `FastAPI APIRouter` with all generic routes. The router is parameterized by the state object (which must have `shesha`, `topic_mgr`, `model` attributes).

Routes to include:
- `GET /api/topics` — list topics with document counts
- `POST /api/topics` — create topic
- `PATCH /api/topics/{name}` — rename topic
- `DELETE /api/topics/{name}` — delete topic
- `GET /api/topics/{name}/traces` — list traces
- `GET /api/topics/{name}/traces/{trace_id}` — get trace detail
- `GET /api/topics/{name}/history` — get conversation history
- `DELETE /api/topics/{name}/history` — clear history
- `GET /api/topics/{name}/export` — export transcript
- `GET /api/model` — get model info
- `PUT /api/model` — update model
- `GET /api/topics/{name}/context-budget` — calculate token budget

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/shared/test_routes.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/routes.py \
        tests/unit/experimental/shared/test_routes.py
git commit -m "feat: extract generic API routes to shared module"
```

---

## Phase 2: Refactor Arxiv Explorer to Use Shared

### Task 7: Refactor web/schemas.py to extend shared

**Files:**
- Modify: `src/shesha/experimental/web/schemas.py`
- Modify: `tests/unit/experimental/web/test_schemas.py`

**Step 1: Read current web/schemas.py**

**Step 2: Update web/schemas.py to import generics from shared**

Remove generic schema definitions. Import them from `shesha.experimental.shared.schemas`. Keep only arxiv-specific schemas (`PaperAdd`, `PaperInfo`, `SearchResult`, `DownloadTaskStatus`). Re-export shared schemas for backward compatibility (existing code that imports from `web.schemas` should still work).

**Step 3: Run existing arxiv schema tests**

Run: `pytest tests/unit/experimental/web/test_schemas.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/web/schemas.py \
        tests/unit/experimental/web/test_schemas.py
git commit -m "refactor: arxiv schemas now extend shared schemas"
```

---

### Task 8: Refactor web/session.py to use shared

**Files:**
- Modify: `src/shesha/experimental/web/session.py`

**Step 1: Update web/session.py**

Replace the session implementation with a thin wrapper or re-export from shared. The arxiv explorer uses `paper_ids` in its WebSocket handler — add a compatibility layer that maps `paper_ids` ↔ `document_ids` at the boundary.

Options:
- **Option A:** `web/session.py` becomes `from shesha.experimental.shared.session import *` with a subclass that adds a `paper_ids` property alias.
- **Option B:** The arxiv websocket handler converts `paper_ids` → `document_ids` before calling the shared handler, and converts back on read.

Choose Option B — it's cleaner. The session itself uses `document_ids`; the arxiv WS handler translates.

**Step 2: Run existing session tests**

Run: `pytest tests/unit/experimental/web/test_session.py -v`
Expected: All PASS (update tests to account for `document_ids` rename if needed)

**Step 3: Commit**

```bash
git add src/shesha/experimental/web/session.py \
        tests/unit/experimental/web/test_session.py
git commit -m "refactor: arxiv session now wraps shared session"
```

---

### Task 9: Refactor web/websockets.py to use shared

**Files:**
- Modify: `src/shesha/experimental/web/websockets.py`

**Step 1: Read current websockets.py**

**Step 2: Refactor to use shared WebSocket handler**

Keep citation-checking logic (`build_citation_instructions`, `_handle_check_citations`, `_check_single_paper`). Replace the generic query/cancel dispatch with the shared handler, passing citation checking as an extra handler:

```python
from shesha.experimental.shared.websockets import websocket_handler as shared_ws_handler

async def websocket_handler(websocket, state):
    await shared_ws_handler(
        websocket,
        state,
        extra_handlers={"check_citations": _handle_check_citations},
        build_context=_build_arxiv_context,
    )
```

Map `paper_ids` → `document_ids` in the context builder.

**Step 3: Run all WebSocket tests**

Run: `pytest tests/unit/experimental/web/test_ws.py tests/unit/experimental/web/test_ws_citations.py tests/experimental/web/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/web/websockets.py
git commit -m "refactor: arxiv WebSocket handler now uses shared handler"
```

---

### Task 10: Refactor web/api.py to use shared

**Files:**
- Modify: `src/shesha/experimental/web/api.py`

**Step 1: Read current api.py**

**Step 2: Refactor to use shared app factory and routes**

Replace the inline `create_api()` with `shared.app_factory.create_app()`. Replace inline topic/trace/history/model routes with the shared router. Keep only arxiv-specific routes (papers, search) as a local router passed to the factory.

**Step 3: Run all arxiv API tests**

Run: `pytest tests/unit/experimental/web/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/web/api.py
git commit -m "refactor: arxiv API now uses shared app factory and routes"
```

---

### Task 11: Full arxiv explorer regression test

**Files:** None (verification only)

**Step 1: Run all backend tests**

Run: `pytest tests/unit/experimental/web/ tests/experimental/web/ -v`
Expected: All PASS

**Step 2: Run frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 3: Run full test suite**

Run: `make all`
Expected: All PASS (format, lint, typecheck, test)

**Step 4: Commit if any fixups were needed**

---

## Phase 3: Shared Frontend Module

### Task 12: Create shared frontend package

**Files:**
- Create: `src/shesha/experimental/shared/frontend/package.json`
- Create: `src/shesha/experimental/shared/frontend/tsconfig.json`
- Create: `src/shesha/experimental/shared/frontend/src/index.ts`

**Step 1: Create package.json**

The shared frontend is a local library package. It does NOT have its own Vite build — consuming apps build it as part of their own Vite pipeline. Use a workspace or path-based import.

```json
{
  "name": "@shesha/shared-ui",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  }
}
```

**Step 2: Create index.ts barrel export**

```typescript
// Components
export { ChatArea } from './components/ChatArea';
export { ChatMessage } from './components/ChatMessage';
export { StatusBar } from './components/StatusBar';
export { TraceViewer } from './components/TraceViewer';
export { Header } from './components/Header';
export { TopicSidebar } from './components/TopicSidebar';
export { ConfirmDialog } from './components/ConfirmDialog';
export { Toast, showToast } from './components/Toast';

// Hooks
export { useWebSocket } from './hooks/useWebSocket';
export { useTheme } from './hooks/useTheme';

// Types
export type * from './types';

// API
export { genericApi } from './api/client';
```

**Step 3: Create tsconfig.json**

Standard strict TypeScript config with JSX support.

**Step 4: Commit**

```bash
git add src/shesha/experimental/shared/frontend/
git commit -m "feat: create shared frontend package skeleton"
```

---

### Task 13: Extract generic TypeScript types

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/types/index.ts`
- Modify: `src/shesha/experimental/web/frontend/src/types/index.ts`
- Reference: existing `types/index.ts` (read first)

**Step 1: Read existing types**

**Step 2: Create shared types**

Move generic interfaces to shared: `TopicInfo`, `TraceStep`, `TraceFull`, `Exchange`, `ContextBudget`, `ModelInfo`, `WSMessage`. Use `documentIds` instead of `paperIds` where applicable.

**Step 3: Update arxiv types to extend shared**

Arxiv types file keeps `PaperInfo`, `SearchResult`, `PaperReport`, citation types. Import and re-export shared types.

**Step 4: Run frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/types/ \
        src/shesha/experimental/web/frontend/src/types/
git commit -m "feat: extract generic TypeScript types to shared frontend"
```

---

### Task 14: Extract generic hooks

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/hooks/useWebSocket.ts`
- Create: `src/shesha/experimental/shared/frontend/src/hooks/useTheme.ts`
- Create: `src/shesha/experimental/shared/frontend/src/hooks/__tests__/useWebSocket.test.ts`
- Reference: existing hooks (read first — both are fully generic)

**Step 1: Read existing hooks and tests**

**Step 2: Copy hooks to shared (they're already generic)**

Both `useWebSocket.ts` and `useTheme.ts` have zero arxiv-specific logic. Copy as-is.

**Step 3: Copy and adapt hook tests**

**Step 4: Update arxiv frontend to import hooks from shared**

Update imports in arxiv `App.tsx` and any component that uses these hooks.

**Step 5: Run tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/hooks/ \
        src/shesha/experimental/web/frontend/src/hooks/ \
        src/shesha/experimental/web/frontend/src/App.tsx
git commit -m "feat: extract hooks to shared frontend"
```

---

### Task 15: Extract fully generic components

StatusBar, ConfirmDialog, Toast, TraceViewer are fully generic — no arxiv references.

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/StatusBar.tsx`
- Create: `src/shesha/experimental/shared/frontend/src/components/ConfirmDialog.tsx`
- Create: `src/shesha/experimental/shared/frontend/src/components/Toast.tsx`
- Create: `src/shesha/experimental/shared/frontend/src/components/TraceViewer.tsx`
- Create corresponding `__tests__/` files
- Modify: arxiv imports to use shared versions

**Step 1: Read existing components and their tests**

**Step 2: Copy components to shared (they're already generic)**

**Step 3: Copy and adapt tests**

**Step 4: Update arxiv frontend imports**

**Step 5: Run tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/ \
        src/shesha/experimental/web/frontend/src/components/
git commit -m "feat: extract generic components (StatusBar, ConfirmDialog, Toast, TraceViewer) to shared"
```

---

### Task 16: Parameterize and extract Header

Header has hardcoded "arXiv Explorer" label and arxiv-specific button labels. Parameterize via props.

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/Header.tsx`
- Create: `src/shesha/experimental/shared/frontend/src/components/__tests__/Header.test.tsx`
- Modify: `src/shesha/experimental/web/frontend/src/components/Header.tsx`

**Step 1: Read existing Header.tsx**

**Step 2: Write failing test for shared Header**

Test that the header renders a configurable `appName` prop and accepts optional action buttons via a `children` or `actions` prop.

Run test, expect FAIL.

**Step 3: Create shared Header**

Props:
```typescript
interface HeaderProps {
  appName: string;
  isDark: boolean;
  onToggleTheme: () => void;
  children?: React.ReactNode;  // Slot for app-specific action buttons
}
```

The shared Header renders: logo, app name, theme toggle, and a slot for app-specific controls. No hardcoded arxiv buttons.

**Step 4: Run test, expect PASS**

**Step 5: Update arxiv Header to compose shared Header**

Arxiv Header wraps the shared Header and passes its search/citation buttons as children.

**Step 6: Run all frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/Header.tsx \
        src/shesha/experimental/shared/frontend/src/components/__tests__/Header.test.tsx \
        src/shesha/experimental/web/frontend/src/components/Header.tsx
git commit -m "feat: extract parameterized Header to shared frontend"
```

---

### Task 17: Parameterize and extract ChatArea and ChatMessage

ChatArea has arxiv-specific `selectedPapers`, `paper_ids`, placeholder text. ChatMessage has arxiv citation parsing. Parameterize both.

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx`
- Create: `src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx`
- Create corresponding tests
- Modify: arxiv versions to wrap shared versions

**Step 1: Read existing ChatArea.tsx and ChatMessage.tsx**

**Step 2: Write failing tests for shared versions**

Shared ChatArea test: renders with generic `selectedDocuments` prop, sends `document_ids` in WebSocket message. Shared ChatMessage test: renders plain answer text without citation parsing.

Run tests, expect FAIL.

**Step 3: Implement shared ChatArea**

Replace `selectedPapers` → `selectedDocuments`, `paper_ids` → `document_ids`. Parameterize placeholder text. Remove arxiv-specific "Select papers" messaging — use a generic `emptySelectionMessage` prop.

```typescript
interface ChatAreaProps {
  topicName: string | null;
  connected: boolean;
  wsSend: (data: object) => void;
  wsOnMessage: (fn: (msg: WSMessage) => void) => () => void;
  onViewTrace: (traceId: string) => void;
  onClearHistory: () => void;
  historyVersion: number;
  selectedDocuments?: Set<string>;
  emptySelectionMessage?: string;
  placeholder?: string;
}
```

**Step 4: Implement shared ChatMessage**

Remove arxiv citation parsing. Accept an optional `renderAnswer` prop for custom answer rendering (arxiv passes its citation renderer, code explorer uses default).

```typescript
interface ChatMessageProps {
  exchange: Exchange;
  onViewTrace: (traceId: string) => void;
  renderAnswer?: (answer: string) => React.ReactNode;
}
```

**Step 5: Run tests, expect PASS**

**Step 6: Update arxiv ChatArea and ChatMessage**

Arxiv ChatArea wraps shared, passing `selectedPapers` as `selectedDocuments` and arxiv-specific messaging. Arxiv ChatMessage wraps shared, passing its citation renderer as `renderAnswer`.

**Step 7: Run all frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 8: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx \
        src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx \
        src/shesha/experimental/shared/frontend/src/components/__tests__/ \
        src/shesha/experimental/web/frontend/src/components/ChatArea.tsx \
        src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx
git commit -m "feat: extract parameterized ChatArea and ChatMessage to shared"
```

---

### Task 18: Parameterize and extract TopicSidebar

TopicSidebar has arxiv `PaperInfo` references and paper-specific rendering. Generalize to "documents" with configurable child item rendering.

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx`
- Create test
- Modify: arxiv version to wrap shared

**Step 1: Read existing TopicSidebar.tsx**

**Step 2: Write failing test for shared TopicSidebar**

Test: renders topics, expands to show generic items, checkboxes toggle selection.

**Step 3: Implement shared TopicSidebar**

```typescript
interface DocumentItem {
  id: string;
  label: string;
  sublabel?: string;
}

interface TopicSidebarProps {
  activeTopic: string | null;
  onSelectTopic: (name: string) => void;
  onTopicsChange: () => void;
  refreshKey: number;
  selectedDocuments: Set<string>;
  onSelectionChange: (selected: Set<string>) => void;
  onDocumentClick: (doc: DocumentItem) => void;
  loadDocuments: (topicName: string) => Promise<DocumentItem[]>;
  addButton?: React.ReactNode;  // Slot for "Add Repo" / "Add Paper" button
  style?: React.CSSProperties;
}
```

The shared sidebar handles topic CRUD, expand/collapse, checkboxes, and delegates document loading to the `loadDocuments` prop. For cross-topic selection (code explorer's requirement), the checkbox state is managed by the parent via `selectedDocuments` / `onSelectionChange`.

**Step 4: Run test, expect PASS**

**Step 5: Update arxiv TopicSidebar to wrap shared**

Arxiv passes a `loadDocuments` that calls `api.papers.list()` and maps `PaperInfo` → `DocumentItem`.

**Step 6: Run all frontend tests**

Expected: All PASS

**Step 7: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TopicSidebar.tsx \
        src/shesha/experimental/shared/frontend/src/components/__tests__/ \
        src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx
git commit -m "feat: extract parameterized TopicSidebar to shared"
```

---

### Task 19: Extract generic API client

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/api/client.ts`
- Create test
- Modify: `src/shesha/experimental/web/frontend/src/api/client.ts`

**Step 1: Read existing client.ts**

**Step 2: Create shared API client**

Extract: `topics.*`, `traces.*`, `history.*`, `model.*`, `contextBudget()`. Keep arxiv-specific endpoints (`papers.*`, `search()`) in the arxiv client.

**Step 3: Update arxiv client to import and extend shared**

**Step 4: Run frontend tests**

Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/api/ \
        src/shesha/experimental/web/frontend/src/api/
git commit -m "feat: extract generic API client to shared frontend"
```

---

### Task 20: Full arxiv regression after frontend extraction

**Step 1: Run all backend tests**

Run: `pytest tests/unit/experimental/web/ tests/experimental/web/ -v`
Expected: All PASS

**Step 2: Run all frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 3: Run full suite**

Run: `make all`
Expected: All PASS

**Step 4: Commit any fixups**

---

## Phase 4: Code Explorer Backend

### Task 21: Create code_explorer module skeleton

**Files:**
- Create: `src/shesha/experimental/code_explorer/__init__.py`
- Create: `src/shesha/experimental/code_explorer/__main__.py`
- Create: `tests/unit/experimental/code_explorer/__init__.py`

**Step 1: Create __init__.py**

```python
"""Shesha Code Explorer — web interface for git repository exploration."""
```

**Step 2: Create minimal __main__.py**

Stub entry point that parses args and prints a placeholder message. Flesh out after routes are built.

```python
"""Code Explorer entry point."""
from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shesha Code Explorer")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    print(f"Code Explorer would start on port {args.port}")


if __name__ == "__main__":
    main()
```

**Step 3: Verify import**

Run: `python -c "import shesha.experimental.code_explorer"`
Expected: No error

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/ \
        tests/unit/experimental/code_explorer/
git commit -m "feat: create code explorer module skeleton"
```

---

### Task 22: Build code explorer dependencies (AppState)

**Files:**
- Create: `src/shesha/experimental/code_explorer/dependencies.py`
- Create: `tests/unit/experimental/code_explorer/test_dependencies.py`
- Reference: `src/shesha/experimental/web/dependencies.py` (read first for pattern)

**Step 1: Read existing web/dependencies.py for pattern**

**Step 2: Write failing test**

Test `create_app_state()` returns a state object with `shesha`, `topic_mgr`, `model` attributes. Mock Shesha initialization.

Run: `pytest tests/unit/experimental/code_explorer/test_dependencies.py -v`
Expected: FAIL

**Step 3: Implement dependencies.py**

```python
@dataclass
class CodeExplorerState:
    shesha: Shesha
    topic_mgr: TopicManager
    model: str
```

`create_app_state()` initializes:
1. Storage directory (default `~/.shesha/code-explorer/` or `--data-dir`)
2. `SheshaConfig` with storage path
3. `Shesha` instance
4. `TopicManager` for repo references per topic

**Step 4: Run test, expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/dependencies.py \
        tests/unit/experimental/code_explorer/test_dependencies.py
git commit -m "feat: code explorer AppState and dependency initialization"
```

---

### Task 23: Build code explorer schemas

**Files:**
- Create: `src/shesha/experimental/code_explorer/schemas.py`
- Create: `tests/unit/experimental/code_explorer/test_schemas.py`

**Step 1: Write failing test**

Test `RepoAdd`, `RepoInfo`, `AnalysisResponse` schema validation.

**Step 2: Implement schemas**

```python
from shesha.experimental.shared.schemas import TopicInfo, ExchangeSchema  # reuse

class RepoAdd(BaseModel):
    url: str
    topic: str | None = None

class RepoInfo(BaseModel):
    project_id: str
    source_url: str
    file_count: int
    analysis_status: str | None  # "current", "stale", "missing"

class AnalysisResponse(BaseModel):
    version: str
    generated_at: str
    head_sha: str
    overview: str
    components: list[dict]
    external_dependencies: list[dict]
    caveats: str

class UpdateStatus(BaseModel):
    status: str  # "unchanged", "updates_available"
    files_ingested: int
```

**Step 3: Run test, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/schemas.py \
        tests/unit/experimental/code_explorer/test_schemas.py
git commit -m "feat: code explorer Pydantic schemas"
```

---

### Task 24: Build code explorer API routes — repo management

**Files:**
- Create: `src/shesha/experimental/code_explorer/api.py`
- Create: `tests/unit/experimental/code_explorer/test_api_repos.py`

**Step 1: Write failing tests**

Test:
- `POST /api/repos` — add repo (mock shesha.create_project_from_repo)
- `GET /api/repos/{id}` — get repo info
- `DELETE /api/repos/{id}` — delete repo
- `POST /api/repos/{id}/check-updates` — check for updates
- `POST /api/repos/{id}/apply-updates` — apply updates
- Singleton behavior: adding same URL twice returns existing project

**Step 2: Implement repo routes**

Use shared `create_app()` factory. Add a code-explorer-specific router with repo routes. Each route delegates to the corresponding `shesha` API method.

Key: `POST /api/repos` must check if the URL is already ingested (singleton behavior). If a `topic` is provided, add the reference.

**Step 3: Run tests, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py \
        tests/unit/experimental/code_explorer/test_api_repos.py
git commit -m "feat: code explorer repo management API routes"
```

---

### Task 25: Build code explorer API routes — analysis

**Files:**
- Modify: `src/shesha/experimental/code_explorer/api.py`
- Create: `tests/unit/experimental/code_explorer/test_api_analysis.py`

**Step 1: Write failing tests**

Test:
- `POST /api/repos/{id}/analyze` — generate analysis (mock shesha.generate_analysis)
- `GET /api/repos/{id}/analysis` — get analysis data
- Analysis for non-existent project returns 404

**Step 2: Implement analysis routes**

**Step 3: Run tests, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py \
        tests/unit/experimental/code_explorer/test_api_analysis.py
git commit -m "feat: code explorer analysis API routes"
```

---

### Task 26: Build code explorer API routes — topic-repo references

**Files:**
- Modify: `src/shesha/experimental/code_explorer/api.py`
- Create: `tests/unit/experimental/code_explorer/test_api_topic_repos.py`

**Step 1: Write failing tests**

Test:
- `POST /api/topics/{name}/repos/{id}` — add repo reference to topic
- `DELETE /api/topics/{name}/repos/{id}` — remove repo reference from topic
- Adding repo to non-existent topic creates the topic
- Removing last reference does NOT delete the repo

**Step 2: Implement topic-repo reference routes**

**Step 3: Run tests, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py \
        tests/unit/experimental/code_explorer/test_api_topic_repos.py
git commit -m "feat: code explorer topic-repo reference routes"
```

---

### Task 27: Build code explorer API routes — global history

**Files:**
- Modify: `src/shesha/experimental/code_explorer/api.py`
- Create: `tests/unit/experimental/code_explorer/test_api_history.py`

**Step 1: Write failing tests**

Test:
- `GET /api/history` — get global conversation history
- `DELETE /api/history` — clear history
- `GET /api/export` — export transcript as markdown

**Step 2: Implement global history routes**

Use the shared `WebConversationSession` with a single global session (not per-topic).

**Step 3: Run tests, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/api.py \
        tests/unit/experimental/code_explorer/test_api_history.py
git commit -m "feat: code explorer global history routes"
```

---

### Task 28: Build code explorer WebSocket handler

**Files:**
- Create: `src/shesha/experimental/code_explorer/websockets.py`
- Create: `tests/unit/experimental/code_explorer/test_ws.py`

**Step 1: Write failing tests**

Test:
- Query with multiple `document_ids` merges documents from multiple projects
- Per-repo analysis is concatenated as context
- Cancel works

**Step 2: Implement WebSocket handler**

Use the shared `websocket_handler()`. Provide a `build_context` function that:
1. Loads analysis for each selected project
2. Formats analyses as context (reuse `format_analysis_as_context` from `script_utils`)
3. Returns the concatenated context string

No extra handlers needed (no citation checking).

**Step 3: Run tests, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/websockets.py \
        tests/unit/experimental/code_explorer/test_ws.py
git commit -m "feat: code explorer WebSocket handler with cross-repo context"
```

---

### Task 29: Complete code explorer entry point

**Files:**
- Modify: `src/shesha/experimental/code_explorer/__main__.py`
- Modify: `pyproject.toml` (add entry point)

**Step 1: Read existing web/__main__.py for pattern**

**Step 2: Complete __main__.py**

Wire up: parse args → create state → create app with shared factory → optionally open browser → run uvicorn on port 8001.

**Step 3: Add entry point to pyproject.toml**

```toml
[project.scripts]
shesha-code = "shesha.experimental.code_explorer.__main__:main"
```

**Step 4: Verify entry point**

Run: `pip install -e ".[web]"` then `shesha-code --help`
Expected: Shows help with --port, --data-dir, --no-browser, --model

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/__main__.py pyproject.toml
git commit -m "feat: code explorer CLI entry point (shesha-code)"
```

---

### Task 30: Code explorer backend regression

Run all code explorer tests plus shared module tests to verify everything integrates.

**Step 1: Run all backend tests**

Run: `pytest tests/unit/experimental/code_explorer/ tests/unit/experimental/shared/ -v`
Expected: All PASS

**Step 2: Run full suite**

Run: `make all`
Expected: All PASS

---

## Phase 5: Code Explorer Frontend

### Task 31: Create code explorer frontend package

**Files:**
- Create: `src/shesha/experimental/code_explorer/frontend/package.json`
- Create: `src/shesha/experimental/code_explorer/frontend/vite.config.ts`
- Create: `src/shesha/experimental/code_explorer/frontend/tsconfig.json`
- Create: `src/shesha/experimental/code_explorer/frontend/index.html`
- Create: `src/shesha/experimental/code_explorer/frontend/src/main.tsx`
- Create: `src/shesha/experimental/code_explorer/frontend/src/index.css`
- Reference: arxiv frontend package.json, vite.config.ts for patterns

**Step 1: Read arxiv frontend config files for patterns**

**Step 2: Create package.json**

Same deps as arxiv (React, Vite, Tailwind, Vitest) minus KaTeX. Add `@shesha/shared-ui` as a local dependency pointing to `../../shared/frontend`.

**Step 3: Create vite.config.ts**

Proxy `/api` to `localhost:8001` (code explorer port). Configure shared UI alias.

**Step 4: Create minimal index.html and main.tsx**

Render a placeholder `<App />` component.

**Step 5: Verify build**

Run: `cd src/shesha/experimental/code_explorer/frontend && npm install && npm run build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/
git commit -m "feat: code explorer frontend package skeleton"
```

---

### Task 32: Build code explorer App.tsx

**Files:**
- Create: `src/shesha/experimental/code_explorer/frontend/src/App.tsx`
- Reference: arxiv `App.tsx` for composition pattern

**Step 1: Read arxiv App.tsx**

Understand how it composes Header, TopicSidebar, ChatArea, StatusBar, TraceViewer.

**Step 2: Write failing test**

Test: App renders with Header showing "Code Explorer", a sidebar, and a chat area.

**Step 3: Implement App.tsx**

Compose shared components:
- `Header` with `appName="Code Explorer"`
- `TopicSidebar` with cross-topic checkbox support and "Add Repo" button
- `ChatArea` with `selectedDocuments` from sidebar state
- `StatusBar`
- `TraceViewer` (conditionally shown as third column)

State management:
- `selectedRepos: Set<string>` — cross-topic selection
- `activeTopic: string | null`
- `traceViewerOpen: boolean`
- `viewingRepoId: string | null` — for inline detail display

**Step 4: Run test, expect PASS**

**Step 5: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/App.tsx \
        src/shesha/experimental/code_explorer/frontend/src/components/__tests__/
git commit -m "feat: code explorer App.tsx composing shared components"
```

---

### Task 33: Build AddRepoModal component

**Files:**
- Create: `src/shesha/experimental/code_explorer/frontend/src/components/AddRepoModal.tsx`
- Create: `src/shesha/experimental/code_explorer/frontend/src/components/__tests__/AddRepoModal.test.tsx`

**Step 1: Write failing test**

Test:
- Modal renders with URL input field
- Optional topic selector (dropdown of existing topics + "Create new" option)
- Submit calls `api.repos.add({ url, topic })`
- Validation: rejects empty URL

**Step 2: Implement AddRepoModal**

Simple modal with:
- URL text input (required)
- Topic dropdown (optional) — loads existing topics, has "New topic..." option
- Submit button
- Cancel button

**Step 3: Run test, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/components/AddRepoModal.tsx \
        src/shesha/experimental/code_explorer/frontend/src/components/__tests__/AddRepoModal.test.tsx
git commit -m "feat: AddRepoModal component for code explorer"
```

---

### Task 34: Build RepoDetail component

**Files:**
- Create: `src/shesha/experimental/code_explorer/frontend/src/components/RepoDetail.tsx`
- Create: `src/shesha/experimental/code_explorer/frontend/src/components/__tests__/RepoDetail.test.tsx`

**Step 1: Write failing test**

Test:
- Renders repo overview, components list, external dependencies
- Shows "No analysis" message when analysis is missing
- Shows "Generate Analysis" button when status is "missing"
- Shows "Regenerate" button when status is "stale"

**Step 2: Implement RepoDetail**

Displays inline in the chat area (like arxiv paper synopsis). Shows:
- Source URL
- File count
- Analysis status badge
- Analysis content (overview, components with paths/APIs, external dependencies)
- Action buttons: "Generate Analysis", "Check for Updates"

**Step 3: Run test, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/components/RepoDetail.tsx \
        src/shesha/experimental/code_explorer/frontend/src/components/__tests__/RepoDetail.test.tsx
git commit -m "feat: RepoDetail component for inline analysis display"
```

---

### Task 35: Build code explorer API client

**Files:**
- Create: `src/shesha/experimental/code_explorer/frontend/src/api/client.ts`
- Create: `src/shesha/experimental/code_explorer/frontend/src/api/__tests__/client.test.ts`

**Step 1: Write failing test**

Test repo-specific API calls: `repos.add()`, `repos.get()`, `repos.delete()`, `repos.checkUpdates()`, `repos.applyUpdates()`, `repos.analyze()`, `repos.getAnalysis()`.

**Step 2: Implement client**

Import and re-export the shared generic API. Add code-explorer-specific endpoints:

```typescript
import { genericApi } from '@shesha/shared-ui';

export const api = {
  ...genericApi,
  repos: {
    add: (data: { url: string; topic?: string }) => fetch('/api/repos', ...),
    get: (id: string) => fetch(`/api/repos/${id}`),
    delete: (id: string) => fetch(`/api/repos/${id}`, { method: 'DELETE' }),
    checkUpdates: (id: string) => fetch(`/api/repos/${id}/check-updates`, { method: 'POST' }),
    applyUpdates: (id: string) => fetch(`/api/repos/${id}/apply-updates`, { method: 'POST' }),
    analyze: (id: string) => fetch(`/api/repos/${id}/analyze`, { method: 'POST' }),
    getAnalysis: (id: string) => fetch(`/api/repos/${id}/analysis`),
  },
  history: {
    get: () => fetch('/api/history'),
    clear: () => fetch('/api/history', { method: 'DELETE' }),
    export: () => fetch('/api/export'),
  },
};
```

**Step 3: Run test, expect PASS**

**Step 4: Commit**

```bash
git add src/shesha/experimental/code_explorer/frontend/src/api/
git commit -m "feat: code explorer API client"
```

---

### Task 36: Frontend integration and build test

**Step 1: Run all code explorer frontend tests**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All PASS

**Step 2: Verify production build**

Run: `cd src/shesha/experimental/code_explorer/frontend && npm run build`
Expected: Build succeeds, outputs to `dist/`

**Step 3: Commit any fixups**

---

## Phase 6: Docker & Deployment

### Task 37: Create Dockerfile

**Files:**
- Create: `code-explorer/Dockerfile`
- Reference: `arxiv-explorer/Dockerfile` (read first — same pattern)

**Step 1: Read existing arxiv Dockerfile**

**Step 2: Create code explorer Dockerfile**

Same multi-stage pattern:
- Stage 1: Node 20, build frontend from `src/shesha/experimental/code_explorer/frontend/`
- Stage 2: Python 3.12-slim, pip install, copy built frontend
- Entry point: `shesha-code --no-browser --data-dir /data`

**Step 3: Commit**

```bash
git add code-explorer/Dockerfile
git commit -m "feat: code explorer Dockerfile"
```

---

### Task 38: Create docker-compose.yml and supporting files

**Files:**
- Create: `code-explorer/docker-compose.yml`
- Create: `code-explorer/code-explorer.sh`
- Create: `code-explorer/README.md`

**Step 1: Read existing arxiv-explorer/ files for pattern**

**Step 2: Create docker-compose.yml**

Port 8001, Docker socket mount, `/data` volume, env vars for `SHESHA_API_KEY` and `SHESHA_MODEL`.

**Step 3: Create startup script and README**

**Step 4: Commit**

```bash
git add code-explorer/
git commit -m "feat: code explorer Docker Compose setup"
```

---

### Task 39: Docker build smoke test

**Step 1: Build the Docker image**

Run: `cd code-explorer && docker compose build`
Expected: Build succeeds

**Step 2: Commit any fixups**

---

## Phase 7: Documentation

### Task 40: Write developer guide

**Files:**
- Create: `docs/extending-web-tools.md`

**Step 1: Write the guide**

Cover:
1. **Overview** — how the shared module works
2. **Quick start** — create a new tool in 5 steps
3. **Backend** — app_factory, shared routes, WebSocket handler, AppState pattern
4. **Frontend** — importing shared components, creating app-specific ones, Vite config
5. **Storage** — conventions for data directory layout
6. **Docker** — Dockerfile pattern, port allocation, docker-compose template
7. **Testing** — red/green/refactor cycle, test patterns, running tests

**Step 2: Commit**

```bash
git add docs/extending-web-tools.md
git commit -m "docs: developer guide for building experimental web tools"
```

---

### Task 41: Update CHANGELOG.md

**Step 1: Add entries under [Unreleased]**

```markdown
### Added
- Code Explorer web application for exploring git repositories via RLM
- Shared web infrastructure module (`shesha.experimental.shared`) for building experimental tools
- Developer guide for extending the web tool ecosystem (`docs/extending-web-tools.md`)

### Changed
- arXiv Explorer refactored to use shared web infrastructure module
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entries for code explorer and shared module"
```

---

## Phase 8: Final Verification

### Task 42: Full regression test

**Step 1: Run complete test suite**

Run: `make all`
Expected: Format, lint, typecheck, ALL tests pass

**Step 2: Run arxiv explorer frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 3: Run code explorer frontend tests**

Run: `cd src/shesha/experimental/code_explorer/frontend && npx vitest run`
Expected: All PASS

**Step 4: Docker build both explorers**

Run: `cd arxiv-explorer && docker compose build`
Run: `cd code-explorer && docker compose build`
Expected: Both build successfully
