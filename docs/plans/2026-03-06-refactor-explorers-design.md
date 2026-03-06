# Design: Extract Shared Explorer Base Classes

## Problem

`DocumentTopicManager` and `CodeExplorerTopicManager` are ~95% identical.
Similar duplication exists in `dependencies.py` (~85%), `api.py` (~70%),
`websockets.py` (~76%), and test files (~450+ duplicate lines). Every bug
fix or feature must be manually duplicated, causing drift.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Public method names | Generic (`add_item`, `list_items`) | All callers are internal to each explorer; no external API to preserve |
| On-disk format | Standardize to `"items"` key | Cleaner than parameterizing; no backward compat (experimental code) |
| Old data migration | None | Experimental code, small user base; old `"docs"`/`"repos"` keys won't load |
| Alias strategy | No aliases | Callers updated to use generic names in same sweep |
| WebSocket scope | Include in this refactor | 76% duplication justifies the effort; callback interface handles divergence |
| ArXiv TopicManager | Excluded | Architecturally different (project-backed, not filesystem-backed) |

## Architecture

### 1. BaseTopicManager

**Location:** `src/shesha/experimental/shared/topics.py`

Concrete class managing topics as filesystem directories containing
`topic.json` files with the format:

```json
{"name": "Reports", "items": ["project-id-1", "project-id-2"]}
```

**Public API:**
- Topic CRUD: `create()`, `rename()`, `delete()`, `list_topics()`, `get_topic_dir()`
- Item refs: `add_item()`, `remove_item()`, `list_items()`, `list_all_items()`, `list_uncategorized()`, `find_topics_for_item()`, `remove_item_from_all()`

**Subclasses** are trivial identity classes (no overrides, no aliases):

```python
class DocumentTopicManager(BaseTopicManager):
    pass

class CodeExplorerTopicManager(BaseTopicManager):
    pass
```

Module-level `_slugify()` and `TOPIC_META_FILE` move to the shared module.

`_read_meta()` only accepts the `"items"` key. Old `"docs"`/`"repos"` files
will fail validation and be treated as corrupt.

### 2. Shared Dependencies

**Location:** `src/shesha/experimental/shared/dependencies.py`

Base state dataclass:

```python
@dataclass
class BaseExplorerState:
    shesha: Shesha
    topic_mgr: BaseTopicManager
    session: WebConversationSession
    model: str
```

`DocumentExplorerState` extends with `uploads_dir: Path`.
`CodeExplorerState` is a thin subclass with no extra fields.

Shared factory `create_app_state()` accepts:
- `app_name: str` — for the home directory path
- `topic_mgr_class: type[BaseTopicManager]` — which subclass to instantiate
- `extra_dirs: dict[str, str] | None` — optional additional directories

`get_topic_session()` moves to the shared module.

Each explorer's `dependencies.py` becomes a thin wrapper calling the
shared factory.

### 3. Shared API Routes

**Location:** `src/shesha/experimental/shared/routes.py` (extend existing)

Shared error mapper:

```python
def _topic_error_to_status(e: ValueError) -> int:
    msg = str(e)
    if "already exists" in msg:
        return 409
    if "not found" in msg.lower():
        return 404
    return 422
```

Route factory returns an `APIRouter` with:
- `POST /topics` — create
- `PATCH /topics/{name}` — rename
- `DELETE /topics/{name}` — delete
- `GET /topics` — list with item counts
- `GET /topics/{name}/items` — list items in topic
- `POST /topics/{name}/items/{project_id}` — add item to topic
- `DELETE /topics/{name}/items/{project_id}` — remove item from topic

Parameterized by a dependency-injection callable that extracts `topic_mgr`
from app state.

Explorer-specific routes stay in each explorer's `api.py`:
- Document explorer: upload, download, metadata, extraction
- Code explorer: repo ingestion, update checking, analysis

### 4. Shared WebSocket Handler

**Location:** `src/shesha/experimental/shared/websockets.py` (extend existing)

New generic multi-project query handler owning the duplicated structure:

1. Validate project IDs
2. Load documents from projects
3. Build context string (via callback)
4. Set up message queue + `on_progress` callback + drain task
5. Resolve RLM engine from loaded projects
6. Execute query via `run_in_executor`
7. Retrieve trace and serialize response

Each explorer provides a callback:

```python
async def build_context(
    state: BaseExplorerState,
    project_ids: list[str],
) -> str
```

Document explorer's reads `meta.json` for filename/content-type context.
Code explorer's fetches analysis overviews.

Each explorer's `websockets.py` shrinks to: define `build_context`, wire
it into the shared handler.

The existing single-project handler stays untouched.

### 5. Test Consolidation

**New shared test files:**
- `tests/unit/experimental/shared/test_topics.py` — full `BaseTopicManager` coverage
- `tests/unit/experimental/shared/test_dependencies.py` — parametrized factory tests
- `tests/unit/experimental/shared/test_routes.py` — shared route tests with minimal test app
- `tests/unit/experimental/shared/test_websockets_multi.py` — multi-project handler with mock callback
- `tests/unit/experimental/shared/conftest.py` — shared fixtures

**Deleted/gutted:**
- Both `test_topics.py` — replaced by shared version
- Duplicated fixtures in `test_api.py` and `test_dependencies.py`

**Kept per-explorer:**
- `test_api.py` — domain-specific routes only
- `test_ws.py` — thin tests verifying correct `build_context` wiring
- `test_extractors.py`, `test_schemas.py` — domain-specific

## Files Changed

**Created:**
- `src/shesha/experimental/shared/topics.py`
- `src/shesha/experimental/shared/dependencies.py`
- `tests/unit/experimental/shared/test_topics.py`
- `tests/unit/experimental/shared/test_dependencies.py`
- `tests/unit/experimental/shared/test_routes.py`
- `tests/unit/experimental/shared/test_websockets_multi.py`
- `tests/unit/experimental/shared/conftest.py`

**Significantly modified:**
- `src/shesha/experimental/shared/routes.py` — topic CRUD + item route factories
- `src/shesha/experimental/shared/websockets.py` — multi-project handler
- `src/shesha/experimental/document_explorer/topics.py` — empty subclass
- `src/shesha/experimental/code_explorer/topics.py` — empty subclass
- `src/shesha/experimental/document_explorer/dependencies.py` — thin wrapper
- `src/shesha/experimental/code_explorer/dependencies.py` — thin wrapper
- `src/shesha/experimental/document_explorer/api.py` — remove topic routes, include shared
- `src/shesha/experimental/code_explorer/api.py` — remove topic routes, include shared
- `src/shesha/experimental/document_explorer/websockets.py` — define callback, use shared handler
- `src/shesha/experimental/code_explorer/websockets.py` — define callback, use shared handler

## Implementation Order

1. `BaseTopicManager` + tests (foundation, zero risk to existing code)
2. Rewrite subclasses + verify existing tests pass
3. Shared dependencies + tests
4. Shared API routes + tests
5. Shared WebSocket handler + tests
6. Delete dead code, clean up

## Risks

1. **WebSockets** — riskiest piece; callback interface must capture all
   divergent behavior. Mitigated by existing 312 tests and TDD approach.
2. **On-disk format break** — existing topic.json files won't load.
   Acceptable for experimental code.
3. **Import paths** — subclasses stay in their original modules, so
   existing imports continue to work.

## Estimated Impact

~1200-1500 lines removed across production and test code.
