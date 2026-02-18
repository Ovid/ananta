# Shared Code Consolidation Design

## Problem

The code-explorer and arxiv-explorer tools have significant code duplication.
The shared module (`src/shesha/experimental/shared/`) provides
`create_shared_router()` with topic CRUD, traces, model management, context
budget, and history routes -- but **neither tool uses it**. Both tools
reimplement all these routes in their own `api.py` files. The arxiv `api.py`
even documents this explicitly:

> The shared `create_shared_router()` is *not* used directly because the arxiv
> explorer has several incompatibilities: the topic listing returns
> `paper_count` (not `document_count`), history is stored in
> `_conversation.json` (not `conversation.json`), and the topic manager does
> not expose `resolve_all()`.

On the frontend, both `App.tsx` files (~385 and ~392 lines) share 60-70%
identical code: state management, WebSocket message handling, sidebar drag,
theme, status bar wiring, connection-loss banner, and layout structure.

This has already caused bugs where a fix to one tool should have been applied
to the other but wasn't, because the code that should be shared isn't shared.

## Goals

1. Make `create_shared_router()` actually usable by both tools.
2. Eliminate duplicated frontend state/handler code.
3. Make it easy to build a third tool quickly.
4. Update `docs/extending-web-tools.md` to reflect reality.

## Approach

**Standardize on generic names.** All tools use `document_count`/`document_ids`
internally. Domain-specific naming (paper_ids, repo_ids) is handled at the
frontend boundary only.

## Backend Design

### Flexible `create_shared_router()`

Add callback parameters to handle the two points of variation:

```python
def create_shared_router(
    state: Any,
    *,
    get_session: Callable[[Any, str], WebConversationSession] | None = None,
    build_topic_info: Callable[[Any], list[TopicInfo]] | None = None,
    resolve_project_ids: Callable[[Any, str], list[str]] | None = None,
) -> APIRouter:
```

**`get_session(state, topic_name)`** -- Returns the conversation session for a
topic. Default: per-project session via `_storage._project_path()`. The
code-explorer overrides this to return `state.session` (global session).

**`build_topic_info(state)`** -- Returns the topic list as `list[TopicInfo]`.
Default: reads from `topic_mgr.list_topics()` with `document_count`. Each tool
can override to build TopicInfo from its own topic manager interface.

**`resolve_project_ids(state, name)`** -- Resolves a topic name to project IDs.
Default: `_resolve_all_project_ids()`. The code-explorer overrides with its
fallback-to-all-projects logic.

### What gets deleted from each tool

Both tools delete their local copies of:
- `_parse_trace_file()` (identical across all three locations)
- Trace list/get routes
- Model get/put routes
- Context budget route
- History/export routes (arxiv per-topic; code-explorer per-topic delegates to global)

### What stays in each tool's `api.py`

**Code-explorer:** Repo CRUD routes, topic CRUD (different interface -- the
code-explorer topic manager returns plain strings, not objects), topic-repo
reference routes, global history routes (`/api/history`, `/api/export`).

**Arxiv:** Paper management, search (arxiv API + local), topic CRUD (can now
use shared version since we standardize on `document_count`).

### Schema changes

- Arxiv `TopicInfo` switches from `paper_count` to `document_count`.
- Arxiv `ExchangeSchema` drops `paper_ids` alias; uses `document_ids` directly.
- The arxiv frontend `TopicSidebar` wrapper can display "papers" in the UI
  while the API uses `document_count`.
- The `_PaperIdAdapter` in `web/websockets.py` is removed — with both
  frontend and backend standardized on `document_ids`, the adapter's
  translation is no longer needed. The `check_citations` WS message keeps
  `paper_ids` as a domain-specific field (not subject to standardization).

## Frontend Design

### `useAppState` hook

Extract into `@shesha/shared-ui`:

```typescript
export function useAppState(options?: {
  onComplete?: () => void
  onExtraMessage?: (msg: any) => void
}) => {
  // Shared state
  dark, toggleTheme,
  connected, send, onMessage,
  modelName,
  tokens, budget, phase, documentBytes,
  sidebarWidth, handleSidebarDrag,
  traceView, setTraceView, handleViewTrace,
  historyVersion, setHistoryVersion,
  activeTopic, setActiveTopic, handleTopicSelect,
}
```

**`onComplete`** -- Called after a query completes. Arxiv uses this to refresh
the context budget. Code-explorer doesn't need it.

**`onExtraMessage`** -- Called for WebSocket messages not handled by the shared
handler (status/step/complete/error/cancelled). Arxiv uses this for
`citation_progress` and `citation_report` messages.

Note: `handleExport` stays domain-specific in each tool's `App.tsx` because
code-explorer export is global (no topic param) while arxiv export is
per-topic.

### Connection-loss banner

Move from both `App.tsx` files into `AppShell` since it's identical.

### What stays in each tool's `App.tsx`

**Code-explorer (~150 lines):** `selectedRepos`, `viewingRepo`, `allRepos`,
`uncategorizedRepos`, `showAddRepo` state; repo handlers (add, analyze, check
updates, remove); `AddRepoModal`/`RepoDetail` rendering.

**Arxiv (~200 lines):** `selectedPapers`, `viewingPaper`, `topicPapersList`
state; citation state and handlers; search/help panels; paper handlers;
domain-specific WS message handling via `onExtraMessage`.

## Documentation Update

Update `docs/extending-web-tools.md` to:
- Document that tools must use `create_shared_router()` with callbacks
- Document the `useAppState` hook
- Remove examples showing manual route implementation for traces/model/budget/history
- Add callback pattern examples
- Verify all other sections still match the codebase

## Estimated Impact

| Area | Before | After | Savings |
|------|--------|-------|---------|
| shared/routes.py | Dead code | Used by both tools | N/A |
| code_explorer/api.py | ~447 lines | ~250 lines | ~200 lines |
| web/api.py | ~494 lines | ~300 lines | ~200 lines |
| code_explorer App.tsx | ~385 lines | ~150 lines | ~235 lines |
| web App.tsx | ~392 lines | ~200 lines | ~192 lines |
| **Total** | | | **~827 lines eliminated** |
