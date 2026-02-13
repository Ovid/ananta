# Code Explorer Web Application — Design

## Overview

A web-based interface for exploring git repositories using Shesha's Recursive
Language Model (RLM). Similar in spirit to the arxiv explorer but focused on
codebases: users add git repos, organize them into optional topics, and query
across repos with full RLM reasoning (sandbox execution, iterative refinement).

The long-term vision includes PRD ingestion and cross-repo HLD-style synthesis,
but this design covers the MVP.

## Approach: Shared-First Extraction

Before building the code explorer, extract generic web infrastructure from the
arxiv explorer into a shared module. The code explorer becomes the second
consumer, validating the abstractions. Both apps import from the shared module,
preventing duplication and drift across the planned ecosystem of experimental
tools.

## Package Structure

```
src/shesha/experimental/
├── shared/                          # Generic web infrastructure
│   ├── __init__.py
│   ├── app_factory.py               # FastAPI app creation (CORS, static files, lifespan)
│   ├── websockets.py                # WebSocket handler (query streaming, cancel)
│   ├── session.py                   # Conversation session (atomic JSON persistence)
│   ├── schemas.py                   # Base Pydantic models (topic, trace, query, history)
│   ├── routes.py                    # Generic topic CRUD as a FastAPI router
│   └── frontend/                    # Shared React components + hooks
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── components/
│           │   ├── ChatArea.tsx
│           │   ├── ChatMessage.tsx
│           │   ├── StatusBar.tsx
│           │   ├── TraceViewer.tsx
│           │   ├── Header.tsx        # Shell with props/slots for app-specific controls
│           │   ├── TopicSidebar.tsx   # Generic: topics with selectable children
│           │   ├── ConfirmDialog.tsx
│           │   └── Toast.tsx
│           ├── hooks/
│           │   ├── useWebSocket.ts
│           │   └── useTheme.ts
│           └── types/
│               └── index.ts          # Shared TypeScript interfaces
│
├── web/                             # arXiv Explorer (refactored to import from shared/)
│   ├── api.py                       # arXiv-specific routes (papers, search, citations)
│   ├── dependencies.py              # AppState with PaperCache, ArxivSearcher
│   ├── schemas.py                   # arXiv-specific schemas (extends shared)
│   ├── websockets.py                # arXiv-specific WS handlers (citation checking)
│   └── frontend/
│       └── src/
│           ├── App.tsx
│           ├── components/           # SearchPanel, PaperDetail, CitationReport, etc.
│           └── api/
│               └── client.ts
│
├── code_explorer/                   # Code Explorer (NEW)
│   ├── __init__.py
│   ├── __main__.py                  # Entry point (shesha-code CLI)
│   ├── api.py                       # Repo-specific routes
│   ├── dependencies.py              # AppState with Shesha (no paper cache)
│   ├── schemas.py                   # Repo-specific schemas
│   └── frontend/
│       └── src/
│           ├── App.tsx
│           ├── components/
│           │   ├── AddRepoModal.tsx
│           │   └── RepoDetail.tsx    # Analysis view (components, deps, overview)
│           └── api/
│               └── client.ts
```

## Data Model & Storage

Storage path: `~/.shesha/code-explorer/` (configurable via `--data-dir`).

```
code-explorer/
├── repos/                          # Global repo clones (one per unique URL)
│   └── Ovid-shesha/                # Pure git clone, zero shesha artifacts
│       ├── .git/
│       ├── src/
│       └── README.md
│
├── projects/                       # Parsed documents per repo
│   └── Ovid-shesha/
│       ├── docs/                   # Parsed JSON documents
│       ├── traces/                 # RLM query traces
│       ├── meta.json               # Project metadata (incl. repo source_url, head_sha)
│       └── analysis.json           # Pre-computed analysis
│
├── topics/                         # Topic metadata (references, not copies)
│   ├── backend/
│   │   └── topic.json              # { "repos": ["Ovid-shesha", "PerlDancer-Dancer2"] }
│   └── frontend/
│       └── topic.json              # { "repos": ["Ovid-shesha"] }
│
└── conversation.json               # Global conversation history
```

### Key invariants

- **Repos are global singletons.** Adding the same URL twice returns the
  existing project. Adding the same repo to a second topic appends a reference.
- **Git clones are pristine.** No shesha metadata inside `repos/`. Repo
  metadata (HEAD SHA, source URL) lives in `projects/{id}/meta.json`.
- **Topics are lightweight.** A `topic.json` with a list of project_ids. No
  file copying, no project duplication.
- **Deleting a repo from a topic** removes the reference. The repo/project is
  only cleaned up when explicitly deleted via the "delete repo" action.
- **Uncategorized repos.** Repos added without a topic appear in an implicit
  "Uncategorized" group.
- **Conversation history is global.** One thread regardless of selected repos
  or topics. Cross-topic queries make per-topic history impractical.
- **No leading underscores** on metadata filenames. The `projects/` and
  `topics/` directories are fully managed by shesha with no collision risk.
  Git clones in `repos/` contain no shesha files at all.
- **Full git clones** (not shallow). The RLM may consult git history to
  understand design decisions and code evolution.

### Known limitation: repo directory naming

Repo directories are named using an `Owner-RepoName` slug (inherited from the
existing `RepoIngester`). This can collide if the same owner/repo path exists
on different hosts (e.g., `github.com/Ovid/shesha` vs `gitlab.com/Ovid/shesha`).
This is a pre-existing limitation in the shesha core — not addressed in this
MVP but worth solving later (e.g., by including the host in the slug).

## Backend Architecture

### Shared backend (`shared/`)

`app_factory.py` provides `create_app(state, static_dir, lifespan)`:
- CORS middleware
- Static file serving (built frontend)
- Mounts shared topic CRUD routes from `routes.py`
- WebSocket endpoint `/api/ws` (query streaming + cancel)

Each app provides an AppState subclass and registers app-specific routes via a
FastAPI router.

### Code explorer AppState

```python
@dataclass
class CodeExplorerState:
    shesha: Shesha
    topic_mgr: TopicManager   # Generalized from arxiv; stores repo references per topic
    model: str
```

No paper cache, no arXiv searcher, no citation verifier.

### API Routes

**Inherited from shared:**
- `GET /api/topics` — List all topics
- `POST /api/topics` — Create topic
- `PATCH /api/topics/{name}` — Rename topic
- `DELETE /api/topics/{name}` — Delete topic (removes references, not repos)
- `GET /api/topics/{name}/traces` — List traces
- `GET /api/topics/{name}/traces/{id}` — Get trace detail
- `GET /api/model` — Get current model info
- `PUT /api/model` — Update model
- `WebSocket /api/ws` — Query streaming + cancel

**Code-explorer-specific:**
- `POST /api/repos` — Add repo (clone + ingest, synchronous). Body: `{ url, topic? }`
- `GET /api/repos/{id}` — Repo info (source URL, file count, analysis status)
- `DELETE /api/repos/{id}` — Delete repo entirely (clone + project + all topic references)
- `POST /api/repos/{id}/check-updates` — Check for new commits
- `POST /api/repos/{id}/apply-updates` — Pull + re-ingest
- `POST /api/repos/{id}/analyze` — Generate/regenerate analysis
- `GET /api/repos/{id}/analysis` — Get analysis data
- `POST /api/topics/{name}/repos/{id}` — Add existing repo to topic
- `DELETE /api/topics/{name}/repos/{id}` — Remove repo from topic (reference only)
- `GET /api/history` — Get global conversation history
- `DELETE /api/history` — Clear global conversation history
- `GET /api/export` — Export global transcript as markdown

**Not included** (vs arxiv explorer): search, paper download tasks, citation
checking, context-budget.

### Cross-repo queries

The WebSocket `query` message includes a list of `project_id`s (not scoped to
one topic). The backend:
1. Merges documents from all selected projects into one RLM query
2. Concatenates each project's per-repo analysis as context
3. Executes a single RLM query against the merged document set

## Frontend Architecture

### Default layout (two columns)

```
┌──────────────────────────────────────────────────────────┐
│  Header: [logo] Code Explorer    [theme toggle] [help]   │
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  Sidebar   │       Main Area                             │
│            │                                             │
│  Topics:   │  Chat conversation + repo detail            │
│  > backend │  (clicking a repo name shows its            │
│    [x] r1  │   analysis inline, like arxiv paper         │
│    [ ] r2  │   synopsis)                                 │
│  > frontend│                                             │
│    [x] r3  │                                             │
│  > uncat.  │                                             │
│    [ ] r4  │                                             │
│            │                                             │
│  [+ Add    │  ┌─────────────────────────────────┐        │
│   Repo]    │  │ Ask a question...               │        │
│            │  └─────────────────────────────────┘        │
├────────────┴─────────────────────────────────────────────┤
│  StatusBar: [model] [tokens] [iteration] [phase]         │
└──────────────────────────────────────────────────────────┘
```

### With trace viewer (three columns, on demand)

```
┌──────────────────────────────────────────────────────────────────┐
│  Header                                                          │
├────────────┬──────────────────────────┬──────────────────────────┤
│  Sidebar   │  Main Area               │  Trace Viewer            │
│            │                          │  - iterations            │
│            │                          │  - code + output         │
│            │                          │  - token counts          │
├────────────┴──────────────────────────┴──────────────────────────┤
│  StatusBar                                                       │
└──────────────────────────────────────────────────────────────────┘
```

### Sidebar behavior

- Topics shown as collapsible groups with checkboxes on each repo
- Checking/unchecking a repo updates the selected set for queries
- Clicking a repo name (not checkbox) shows its analysis inline in the main area
- "Add Repo" opens a modal: paste URL, optionally assign to a topic or create one
- Topic CRUD: rename, delete (removes references, not repos), create
- Repos with no topic appear under "Uncategorized"

### Component ownership

**Shared** (from `shared/frontend/`):
ChatArea, ChatMessage, StatusBar, TraceViewer, Header, TopicSidebar,
ConfirmDialog, Toast, useWebSocket, useTheme

**Code-explorer-specific:**
AddRepoModal (URL input, optional topic selector), RepoDetail (analysis display
rendered inline), app-specific API client

## Shared Module Extraction

What moves from `web/` to `shared/`:

| Current (`web/`) | Target (`shared/`) | Notes |
|---|---|---|
| `websockets.py` query/cancel logic | `websockets.py` | Strip citation-checking; arxiv adds back |
| `session.py` | `session.py` | Already generic |
| `schemas.py` base models | `schemas.py` | Arxiv/code extend with domain models |
| App creation boilerplate | `app_factory.py` | CORS, static files, lifespan |
| Topic CRUD routes | `routes.py` | Generic router |

What moves on the frontend:

| Component | Notes |
|---|---|
| ChatArea, ChatMessage | Generic markdown + KaTeX rendering |
| StatusBar | Generic tokens/phase/iteration display |
| TraceViewer | Generic step-by-step viewer |
| Header | Parameterized via props for app name + controls |
| ConfirmDialog, Toast | Generic utilities |
| useWebSocket, useTheme | Generic hooks |
| Shared TypeScript types | Base interfaces |

What stays in `web/` (arxiv-specific): SearchPanel, PaperDetail,
CitationReport, DownloadProgress, EmailModal, citation WS handler,
PaperCache/ArxivSearcher in AppState.

Shared frontend is a local package (workspace dependency or Vite alias), not
published to npm.

## Docker & Deployment

```
code-explorer/
├── Dockerfile              # Multi-stage: Node 20 frontend + Python 3.12
├── docker-compose.yml      # Port 8001, Docker socket mount, /data volume
├── code-explorer.sh        # Startup script
└── README.md
```

Entry point in `pyproject.toml`:
```
shesha-code = "shesha.experimental.code_explorer.__main__:main"
```

Port 8001 to avoid collision with arxiv explorer (8000).

Docker mode supports remote git URLs only (GitHub, GitLab, Bitbucket). Local
paths work only when running outside Docker (development mode).

## Constraints & Scope

**MVP includes:**
- Public git repos only (no auth tokens)
- Manual update checking (user clicks "check for updates")
- Synchronous repo cloning (user waits for clone + ingest)
- Per-repo analysis using existing shesha API
- Cross-topic repo selection with merged documents in one query
- Global conversation history

**MVP excludes:**
- Search functionality
- Private repo authentication
- Automatic update detection
- Async repo cloning
- Cross-repo synthesis / HLD generation
- PRD ingestion

**Future direction:** PRD ingestion, cross-repo HLD-style synthesis (building
on the existing `multi_repo/` analyzer patterns), private repo auth.

## Documentation

A developer guide at `docs/extending-web-tools.md` covering:
- How the shared module works (app_factory, shared routes, WebSocket handler)
- Step-by-step: creating a new experimental web tool on the Shesha backend
- Importing and composing shared React components
- Dockerfile + docker-compose conventions
- Storage layout, naming, port allocation

## Testing Strategy

All code follows the red/green/refactor cycle:

1. **RED:** Write a failing test first. Run it. Confirm it fails.
2. **GREEN:** Write the minimum code to make the test pass. Nothing extra.
3. **REFACTOR:** Clean up while keeping tests green.
4. **COMMIT:** After each green state.

Test areas:

- **Shared module:** Unit tests for session persistence, WebSocket handler,
  schema validation, app factory
- **Code explorer backend:** API route tests (repo CRUD, update check,
  analysis, topic-repo references), storage model tests (singleton repos,
  topic references, cleanup on delete)
- **Code explorer frontend:** Vitest + React Testing Library for AddRepoModal,
  RepoDetail, TopicSidebar with cross-topic checkboxes
- **Arxiv explorer regression:** Existing tests must pass after extraction
- **Integration:** Docker build test

## Reuse Policy

Before writing any code that looks like it could already exist in the codebase,
check whether an existing implementation can be reused or adapted. This applies
to utility functions, patterns, React components, API helpers, and test
fixtures. When uncertain whether something should be reused or written fresh,
surface the question rather than guessing.
