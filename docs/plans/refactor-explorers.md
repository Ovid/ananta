# Refactor: Extract Shared Explorer Base Classes

## Problem

`DocumentTopicManager` and `CodeExplorerTopicManager` are ~95% identical.
The only meaningful difference is the TypedDict key name (`"docs"` vs `"repos"`).
Every bug fix or feature added to one must be manually duplicated in the other,
which has already led to drift and review comments catching inconsistencies.

## Scope

### 1. BaseTopicManager

Extract a shared `BaseTopicManager` into `src/shesha/experimental/shared/topics.py`.
Parameterize on the item key name so subclasses only declare:

```python
class DocumentTopicManager(BaseTopicManager):
    _ITEM_KEY = "docs"

class CodeExplorerTopicManager(BaseTopicManager):
    _ITEM_KEY = "repos"
```

**Methods to lift into the base class (all currently identical or near-identical):**

| Method | Difference |
|---|---|
| `_slugify()` (module-level) | None — identical |
| `_validate_name()` | None — identical |
| `create()` | Key name in TypedDict init |
| `rename()` | None — identical |
| `delete()` | None — identical |
| `list_topics()` | None — identical |
| `add_doc` / `add_repo` → `add_item()` | Method name only |
| `remove_doc` / `remove_repo` → `remove_item()` | Method name only |
| `list_docs` / `list_repos` → `list_items()` | Method name only |
| `list_all_docs` / `list_all_repos` → `list_all_items()` | Method name only |
| `list_uncategorized_docs` / `list_uncategorized_repos` | Method name only |
| `find_topics_for_doc` / `find_topics_for_repo` | Method name only |
| `remove_doc_from_all` / `remove_repo_from_all` | Method name only |
| `get_topic_dir()` | None — identical |
| `_resolve()` | None — identical |
| `_iter_topic_dirs()` | None — identical |
| `_read_meta()` | Validates `_ITEM_KEY` instead of hardcoded key |

The subclasses should keep their existing public method names (e.g.
`add_doc`, `list_repos`) as thin wrappers or aliases so callers don't
need to change.

### 2. ArXiv TopicManager — excluded

`ArxivTopicManager` is architecturally different (project-backed via
Shesha storage, not filesystem-backed). It does not share enough code
to justify a common base with the other two. Leave it separate.

Note: the ArXiv `_slugify` is simpler (no `unicodedata.normalize`) and
its `_validate_name` is missing entirely. Consider aligning these
independently if the ArXiv explorer gains user-facing topic creation.

### 3. Look for other duplication

Before starting, audit the following for similar cross-explorer
duplication that could be consolidated at the same time:

- [ ] `websockets.py` — document loading loop, progress drain,
      engine resolution, and session recording are structurally
      similar across document_explorer and code_explorer
- [ ] `api.py` — topic CRUD routes, document/repo CRUD routes,
      error handling patterns (the 404/409/422 mapping we just fixed)
- [ ] `dependencies.py` / state classes — check if the state
      dataclasses share fields that could be extracted
- [ ] `frontend/` — shared components already live in
      `shared/frontend/`; verify nothing has drifted back into
      explorer-specific frontends
- [ ] Test helpers — `_make_state()`, `_make_doc()`, fixture
      patterns across test files

## Approach

1. Create `src/shesha/experimental/shared/topics.py` with `BaseTopicManager`
2. Write tests for the base class directly (parameterized on item key)
3. Rewrite `DocumentTopicManager` and `CodeExplorerTopicManager` as
   thin subclasses
4. Verify all existing tests pass without modification (public API
   must not change)
5. Remove duplicated code from both explorer topic modules

## Risks

- **Public API stability:** Callers use `add_doc()`, `list_repos()`,
  etc. These names must be preserved (aliases or overrides).
- **Import paths:** Nothing outside the experimental modules imports
  these directly, but check before moving.
- **TypedDict shape:** The base class `_read_meta` must validate the
  correct key per subclass. Using `_ITEM_KEY` as a class variable
  keeps this clean.
