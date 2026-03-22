# Extending the Web Tool Ecosystem

This guide walks through creating a new explorer using the shared
infrastructure in `src/ananta/explorers/shared_ui/`.

Existing tools built on this infrastructure:

- **arXiv Explorer** (`ananta.explorers.arxiv`) -- search, download, and query arXiv papers
- **Code Explorer** (`ananta.explorers.code`) -- ingest and query git repositories

## 1. Overview

The shared module provides two layers of reusable infrastructure:

**Backend** (`src/ananta/explorers/shared_ui/`):

| Module            | Purpose                                                       |
|-------------------|---------------------------------------------------------------|
| `app_factory.py`  | `create_app()` -- FastAPI factory with lifespan, CORS, static |
| `routes.py`       | `create_shared_router()` -- topic CRUD, traces, history, model, context budget |
| `schemas.py`      | Pydantic models shared across tools                           |
| `session.py`      | `WebConversationSession` -- JSON-persisted conversation history |
| `websockets.py`   | `websocket_handler()` -- query dispatch loop with cancellation |

**Frontend** (`src/ananta/explorers/shared_ui/frontend/`, published as `@ananta/shared-ui`):

| Export             | Purpose                                         |
|--------------------|-------------------------------------------------|
| `Header`           | App header with theme toggle                    |
| `TopicSidebar`     | Topic list with document selection               |
| `ChatArea`         | Message list with input, trace links, streaming  |
| `ChatMessage`      | Individual Q&A message with markdown             |
| `StatusBar`        | Token count, context budget, model display       |
| `TraceViewer`      | Expandable step timeline for query traces        |
| `ToastContainer`   | Toast notifications                              |
| `ConfirmDialog`    | Modal confirmation dialog                        |
| `AppShell`         | Root layout shell with connection-loss banner     |
| `useTheme`         | Dark/light theme hook                            |
| `useWebSocket`     | WebSocket connection hook with reconnect         |
| `useAppState`      | Shared state hook (theme, WS, model, tokens, sidebar, topics) |
| `sharedApi`        | API client for shared routes (topics, traces, model, history) |

## 2. Quick Start -- Create a New Tool in 5 Steps

### Step 1: Create the backend module

```
src/ananta/explorers/your_tool/
    __init__.py
    __main__.py      # CLI entry point
    dependencies.py  # AppState dataclass + create_app_state()
    api.py           # create_api() using shared app factory
    schemas.py       # Tool-specific Pydantic models
    topics.py        # Tool-specific topic manager (if needed)
    websockets.py    # Custom WS handler (if needed)
```

### Step 2: Wire up the backend

Create an `AppState` dataclass, `create_app_state()` factory, and `create_api()`
function. See Section 3 for details.

### Step 3: Create the frontend

```
src/ananta/explorers/your_tool/frontend/
    package.json     # depends on @ananta/shared-ui
    vite.config.ts
    src/
        App.tsx
        api.ts       # extends sharedApi
        ...
```

### Step 4: Create Docker deployment

```
your-tool/
    Dockerfile
    docker-compose.yml
```

### Step 5: Register the entry point

Add to `pyproject.toml`:

```toml
[project.scripts]
ananta-yourtool = "ananta.explorers.your_tool.__main__:main"
```

## 3. Backend

### AppState pattern

Every tool defines a dataclass holding its shared state. The shared routes and
WebSocket handler access fields by attribute name, so these fields are required:

```python
from dataclasses import dataclass
from ananta import Ananta
from ananta.explorers.shared_ui.session import WebConversationSession

@dataclass
class YourToolState:
    ananta: Ananta                  # Required -- lifespan calls start()/stop()
    topic_mgr: YourTopicManager     # Required -- shared routes use this
    session: WebConversationSession  # Required for global history
    model: str                      # Required -- model get/set routes use this
```

The `create_app_state()` factory initializes all components:

```python
def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> YourToolState:
    data_dir = data_dir or Path.home() / ".ananta" / "your-tool"
    ananta_data = data_dir / "ananta_data"
    topics_dir = data_dir / "topics"
    ananta_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    config = AnantaConfig.load(storage_path=str(ananta_data))
    if model:
        config.model = model

    storage = FilesystemStorage(ananta_data)
    ananta = Ananta(config=config, storage=storage)
    topic_mgr = YourTopicManager(topics_dir)
    session = WebConversationSession(data_dir)

    return YourToolState(
        ananta=ananta, topic_mgr=topic_mgr,
        session=session, model=config.model,
    )
```

### App factory

`create_app()` builds a FastAPI instance with common middleware:

```python
from ananta.explorers.shared_ui.app_factory import create_app

app = create_app(
    state,
    title="Ananta Your Tool",
    static_dir=Path("frontend/dist"),   # SPA catch-all (optional)
    images_dir=Path("images"),           # mounted at /static (optional)
    ws_handler=lambda ws: my_ws(ws, state),  # /api/ws (optional)
    extra_routers=[my_router],           # tool-specific routes
)
```

What it provides automatically:

- Lifespan hook calling `state.ananta.start()` / `state.ananta.stop()`
- CORS middleware (allow all origins)
- `.well-known` catch-all (suppresses Chrome DevTools probes)
- Optional WebSocket endpoint at `/api/ws`
- Optional static file serving

### Shared routes

`create_shared_router()` provides topic CRUD, traces, history, model, and
context budget routes. Both the arXiv and code explorer use it via callbacks
to adapt the shared routes to their domain models:

```python
from ananta.explorers.shared_ui.routes import create_shared_router

shared_router = create_shared_router(
    state,
    # Callbacks to customize behavior (all optional):
    build_topic_info=my_topic_builder,     # list[TopicInfo] from your state
    get_session=my_session_factory,        # session for a given topic name
    resolve_project_ids=my_id_resolver,    # project IDs for trace aggregation
    list_trace_files=my_trace_lister,      # trace files for a project
    # Feature flags:
    include_topic_crud=True,               # /api/topics CRUD routes
    include_per_topic_history=True,        # /api/topics/{name}/history
    include_context_budget=True,           # /api/topics/{name}/context-budget
)
```

**Callbacks:** When omitted, the shared router uses sensible defaults that
call `state.topic_mgr` methods directly. Provide callbacks when your topic
manager has a different interface or when you need custom mapping:

```python
# Example: code explorer maps topics to repo lists
def _build_code_topic_info(state: CodeExplorerState) -> list[TopicInfo]:
    return [
        TopicInfo(name=n, document_count=len(state.topic_mgr.list_repos(n)),
                  size="", project_id=f"topic:{n}")
        for n in state.topic_mgr.list_topics()
    ]

# Example: code explorer uses per-topic sessions stored in topic dirs
def _get_topic_session(state, topic_name: str):
    _meta, meta_path = state.topic_mgr._resolve(topic_name)
    return WebConversationSession(meta_path.parent)
```

**Feature flags:** Use `include_topic_crud=False` when your tool has
different topic semantics (the code explorer manages topics via its own
repo router). The arXiv explorer uses the defaults for all flags.

### Extra routers

Tool-specific routes go on a separate `APIRouter` passed via `extra_routers`:

```python
def _create_tool_router(state: YourToolState) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/your-resource")
    def list_resources() -> list[dict[str, str]]:
        ...

    return router

def create_api(state: YourToolState) -> FastAPI:
    tool_router = _create_tool_router(state)
    return create_app(
        state,
        title="Ananta Your Tool",
        ws_handler=lambda ws: handle_ws(ws, state),
        extra_routers=[tool_router],
    )
```

### WebSocket handler

The shared `websocket_handler()` handles the dispatch loop (query, cancel) and
accepts two extension points:

```python
from ananta.explorers.shared_ui.websockets import websocket_handler

await websocket_handler(
    websocket, state,
    extra_handlers={"check_citations": handle_citations},  # custom messages
    build_context=my_context_builder,  # appends context to user question
)
```

If your tool needs fundamentally different query semantics (e.g., cross-project
queries like the code explorer), write a custom WebSocket handler instead.
Follow the same pattern: accept/cancel loop, `asyncio.Queue` for thread-safe
progress streaming, `run_in_executor` for the blocking RLM query.

### Entry point

The `__main__.py` wires CLI arguments to `create_app_state()` and `create_api()`:

```python
import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

def main() -> None:
    parser = argparse.ArgumentParser(description="Ananta Your Tool")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--open", action="store_true", help="Open browser on startup")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--bind", type=str, default="127.0.0.1")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)

    url = f"http://{args.bind}:{args.port}"
    print(f"\n  Ananta Your Tool → {url}\n")

    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.bind, port=args.port)
```

## 4. Frontend

### Package setup

Your frontend's `package.json` references the shared UI as a local dependency:

```json
{
  "dependencies": {
    "@ananta/shared-ui": "file:../../shared/frontend",
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  }
}
```

### App shell and state management

`AppShell` provides the root layout and connection-loss banner. `useAppState`
extracts all common state management (theme, WebSocket, model loading, tokens,
sidebar drag, topic selection, trace viewing) into a single hook:

```tsx
import { AppShell, useAppState, StatusBar, TraceViewer, ToastContainer, showToast } from '@ananta/shared-ui'

export default function App() {
  const {
    dark, toggleTheme, connected, send, onMessage,
    modelName, tokens, budget, setBudget, phase, setPhase, documentBytes,
    sidebarWidth, handleSidebarDrag,
    activeTopic, handleTopicSelect: baseHandleTopicSelect,
    traceView, setTraceView, handleViewTrace,
    historyVersion, setHistoryVersion, setTokens,
  } = useAppState({
    onComplete: () => { /* refresh budget, etc. */ },
    onExtraMessage: (msg) => {
      // Handle tool-specific WS messages (e.g., citation progress).
      // Error messages are delegated here exclusively when provided —
      // call setPhase('Error') yourself if desired.
      if (msg.type === 'error') {
        setPhase('Error')
        showToast(msg.message ?? 'Unknown error', 'error')
      }
    },
  })

  return (
    <AppShell connected={connected}>
      {/* Your tool's UI */}
      <StatusBar topicName={activeTopic} modelName={modelName} tokens={tokens}
        budget={budget} phase={phase} documentBytes={documentBytes} />
    </AppShell>
  )
}
```

### Importing shared components

Import components from `@ananta/shared-ui` and adapt as needed:

```tsx
import { Header, TopicSidebar, ChatArea, ChatMessage, StatusBar,
  TraceViewer, ToastContainer, ConfirmDialog } from '@ananta/shared-ui'
```

The shared components accept props for domain-specific customization. For
example, `TopicSidebar` accepts `loadDocuments` and `DocumentItem` callbacks so
the arXiv explorer can show papers while the code explorer shows repos.

### API client

Extend `sharedApi` with tool-specific endpoints:

```ts
import { request, sharedApi } from '@ananta/shared-ui'

export const api = {
  ...sharedApi,
  repos: {
    list: () => request<RepoInfo[]>('/repos'),
    add: (url: string, topic?: string) =>
      request<{ project_id: string }>('/repos', {
        method: 'POST',
        body: JSON.stringify({ url, topic }),
      }),
  },
}
```

### Vite configuration

Two critical settings:

1. **Proxy `/api` to your backend** for development
2. **Alias `react` and `react-dom`** to prevent duplicate React instances
   (the shared-ui package is a local file dependency, so without aliases both
   copies of React would be bundled)

```ts
import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      react: path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
    css: false,
  },
})
```

## 5. Storage Conventions

Each tool stores data under `~/.ananta/<tool-name>/` by default (overridden via
`--data-dir`). Standard layout:

```
~/.ananta/your-tool/
    ananta_data/         # Ananta storage (documents, traces, analyses)
    topics/              # Topic manager data
    conversation.json    # Global conversation session
```

Rules:

- No leading underscores on metadata files. The arXiv explorer's legacy
  `_conversation.json` predates this convention.
- The `ananta_data/` subdirectory is passed to `AnantaConfig.load(storage_path=...)`
  and `FilesystemStorage()`.
- Topics are stored under `topics/` with tool-specific structure (e.g.,
  `topic.json` in the code explorer, directory-per-topic in the arXiv explorer).

## 6. Docker Pattern

### Multi-stage build

```dockerfile
# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend
WORKDIR /build

# Copy shared UI library first (local dependency)
COPY src/ananta/explorers/shared_ui/frontend/ /shared-ui/

# Copy tool frontend
COPY src/ananta/explorers/your_tool/frontend/package.json \
     src/ananta/explorers/your_tool/frontend/package-lock.json ./

# Rewrite the local dependency path for the Docker build context
RUN sed -i 's|file:../../shared/frontend|file:/shared-ui|' package.json

RUN npm ci --silent
COPY src/ananta/explorers/your_tool/frontend/ ./
RUN npm run build

# --- Stage 2: Runtime ---
FROM python:3.12-slim
WORKDIR /app
COPY . .

# Copy built frontend into the source tree
COPY --from=frontend /build/dist src/ananta/explorers/your_tool/frontend/dist

ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8002
ENTRYPOINT ["ananta-yourtool", "--data-dir", "/data"]
```

Key points:

- The shared frontend must be copied into the build stage so that
  `@ananta/shared-ui` resolves during `npm ci`.
- The `sed` command rewrites the local file path to match the Docker layout.
- `SETUPTOOLS_SCM_PRETEND_VERSION` is needed because `.git` is excluded by
  `.dockerignore`.

### docker-compose

```yaml
services:
  ananta-yourtool:
    build:
      context: ..                          # project root
      dockerfile: your-tool/Dockerfile
    ports:
      - "8002:8002"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ananta-yourtool-data:/data
    environment:
      - ANANTA_API_KEY=${ANANTA_API_KEY:?Set ANANTA_API_KEY}
      - ANANTA_MODEL=${ANANTA_MODEL:?Set ANANTA_MODEL}

volumes:
  ananta-yourtool-data:
```

The build context must be the project root (not the tool directory) because the
Dockerfile copies from `src/ananta/explorers/`.

## 7. Testing

### Mandatory TDD

All code follows the red-green-refactor cycle. See `CLAUDE.md` for the full
policy.

### Backend tests

Use pytest with `MagicMock` for the Ananta instance and a real topic manager
backed by `tmp_path`:

```python
from unittest.mock import MagicMock
from ananta.explorers.your_tool.dependencies import YourToolState

def test_list_repos(tmp_path):
    ananta = MagicMock()
    ananta.list_projects.return_value = ["proj-1"]
    topic_mgr = YourTopicManager(tmp_path / "topics")
    state = YourToolState(ananta=ananta, topic_mgr=topic_mgr, ...)
    # test route behavior using TestClient
```

Run the full backend suite:

```bash
make all   # format + lint + typecheck + test
```

### Frontend tests

Use Vitest with React Testing Library. Mock the API client and shared hooks:

```ts
import { vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    repos: { list: vi.fn().mockResolvedValue([]) },
  },
}))
```

Run frontend tests:

```bash
cd src/ananta/explorers/your_tool/frontend
npm test
```
