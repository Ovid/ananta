# Extending the Web Tool Ecosystem

This guide walks through creating a new experimental web tool using the shared
infrastructure in `src/shesha/experimental/shared/`.

Existing tools built on this infrastructure:

- **arXiv Explorer** (`shesha.experimental.web`) -- search, download, and query arXiv papers
- **Code Explorer** (`shesha.experimental.code_explorer`) -- ingest and query git repositories

## 1. Overview

The shared module provides two layers of reusable infrastructure:

**Backend** (`src/shesha/experimental/shared/`):

| Module            | Purpose                                                       |
|-------------------|---------------------------------------------------------------|
| `app_factory.py`  | `create_app()` -- FastAPI factory with lifespan, CORS, static |
| `routes.py`       | `create_shared_router()` -- topic CRUD, traces, history, model, context budget |
| `schemas.py`      | Pydantic models shared across tools                           |
| `session.py`      | `WebConversationSession` -- JSON-persisted conversation history |
| `websockets.py`   | `websocket_handler()` -- query dispatch loop with cancellation |

**Frontend** (`src/shesha/experimental/shared/frontend/`, published as `@shesha/shared-ui`):

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
| `useTheme`         | Dark/light theme hook                            |
| `useWebSocket`     | WebSocket connection hook with reconnect         |
| `sharedApi`        | API client for shared routes (topics, traces, model, history) |

## 2. Quick Start -- Create a New Tool in 5 Steps

### Step 1: Create the backend module

```
src/shesha/experimental/your_tool/
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
src/shesha/experimental/your_tool/frontend/
    package.json     # depends on @shesha/shared-ui
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
shesha-yourtool = "shesha.experimental.your_tool.__main__:main"
```

## 3. Backend

### AppState pattern

Every tool defines a dataclass holding its shared state. The shared routes and
WebSocket handler access fields by attribute name, so these fields are required:

```python
from dataclasses import dataclass
from shesha import Shesha
from shesha.experimental.shared.session import WebConversationSession

@dataclass
class YourToolState:
    shesha: Shesha                  # Required -- lifespan calls start()/stop()
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
    data_dir = data_dir or Path.home() / ".shesha" / "your-tool"
    shesha_data = data_dir / "shesha_data"
    topics_dir = data_dir / "topics"
    shesha_data.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model

    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    topic_mgr = YourTopicManager(topics_dir)
    session = WebConversationSession(data_dir)

    return YourToolState(
        shesha=shesha, topic_mgr=topic_mgr,
        session=session, model=config.model,
    )
```

### App factory

`create_app()` builds a FastAPI instance with common middleware:

```python
from shesha.experimental.shared.app_factory import create_app

app = create_app(
    state,
    title="Shesha Your Tool",
    static_dir=Path("frontend/dist"),   # SPA catch-all (optional)
    images_dir=Path("images"),           # mounted at /static (optional)
    ws_handler=lambda ws: my_ws(ws, state),  # /api/ws (optional)
    extra_routers=[my_router],           # tool-specific routes
)
```

What it provides automatically:

- Lifespan hook calling `state.shesha.start()` / `state.shesha.stop()`
- CORS middleware (allow all origins)
- `.well-known` catch-all (suppresses Chrome DevTools probes)
- Optional WebSocket endpoint at `/api/ws`
- Optional static file serving

### Shared routes

If your topic manager follows the same interface as the arXiv explorer's
(`.list_topics()`, `.resolve()`, `.create()`, `.rename()`, `.delete()`,
`._storage`), you can use `create_shared_router()` to get topic CRUD, traces,
history, model, and context budget routes for free:

```python
from shesha.experimental.shared.routes import create_shared_router

shared_router = create_shared_router(
    state,
    include_per_topic_history=True,    # /api/topics/{name}/history
    include_context_budget=True,       # /api/topics/{name}/context-budget
)
```

If your tool's domain model differs (e.g., `paper_count` vs `document_count`),
define your own routes in a local `APIRouter` instead. The arXiv explorer
takes this approach.

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
        title="Shesha Your Tool",
        ws_handler=lambda ws: handle_ws(ws, state),
        extra_routers=[tool_router],
    )
```

### WebSocket handler

The shared `websocket_handler()` handles the dispatch loop (query, cancel) and
accepts two extension points:

```python
from shesha.experimental.shared.websockets import websocket_handler

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
    parser = argparse.ArgumentParser(description="Shesha Your Tool")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
```

## 4. Frontend

### Package setup

Your frontend's `package.json` references the shared UI as a local dependency:

```json
{
  "dependencies": {
    "@shesha/shared-ui": "file:../../shared/frontend",
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  }
}
```

### Importing shared components

Import from `@shesha/shared-ui` and adapt as needed:

```tsx
import {
  Header,
  TopicSidebar,
  ChatArea,
  StatusBar,
  TraceViewer,
  ToastContainer,
  ConfirmDialog,
  useTheme,
  useWebSocket,
  sharedApi,
} from '@shesha/shared-ui'
```

The shared components accept props for domain-specific customization. For
example, `TopicSidebar` accepts `loadDocuments` and `DocumentItem` callbacks so
the arXiv explorer can show papers while the code explorer shows repos.

### API client

Extend `sharedApi` with tool-specific endpoints:

```ts
import { request, sharedApi } from '@shesha/shared-ui'

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

Each tool stores data under `~/.shesha/<tool-name>/` by default (overridden via
`--data-dir`). Standard layout:

```
~/.shesha/your-tool/
    shesha_data/         # Shesha storage (documents, traces, analyses)
    topics/              # Topic manager data
    conversation.json    # Global conversation session
```

Rules:

- No leading underscores on metadata files. The arXiv explorer's legacy
  `_conversation.json` predates this convention.
- The `shesha_data/` subdirectory is passed to `SheshaConfig.load(storage_path=...)`
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
COPY src/shesha/experimental/shared/frontend/ /shared-ui/

# Copy tool frontend
COPY src/shesha/experimental/your_tool/frontend/package.json \
     src/shesha/experimental/your_tool/frontend/package-lock.json ./

# Rewrite the local dependency path for the Docker build context
RUN sed -i 's|file:../../shared/frontend|file:/shared-ui|' package.json

RUN npm ci --silent
COPY src/shesha/experimental/your_tool/frontend/ ./
RUN npm run build

# --- Stage 2: Runtime ---
FROM python:3.12-slim
WORKDIR /app
COPY . .

# Copy built frontend into the source tree
COPY --from=frontend /build/dist src/shesha/experimental/your_tool/frontend/dist

ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8002
ENTRYPOINT ["shesha-yourtool", "--no-browser", "--data-dir", "/data"]
```

Key points:

- The shared frontend must be copied into the build stage so that
  `@shesha/shared-ui` resolves during `npm ci`.
- The `sed` command rewrites the local file path to match the Docker layout.
- `SETUPTOOLS_SCM_PRETEND_VERSION` is needed because `.git` is excluded by
  `.dockerignore`.

### docker-compose

```yaml
services:
  shesha-yourtool:
    build:
      context: ..                          # project root
      dockerfile: your-tool/Dockerfile
    ports:
      - "8002:8002"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - shesha-yourtool-data:/data
    environment:
      - SHESHA_API_KEY=${SHESHA_API_KEY:?Set SHESHA_API_KEY}
      - SHESHA_MODEL=${SHESHA_MODEL:?Set SHESHA_MODEL}

volumes:
  shesha-yourtool-data:
```

The build context must be the project root (not the tool directory) because the
Dockerfile copies from `src/shesha/experimental/`.

## 7. Testing

### Mandatory TDD

All code follows the red-green-refactor cycle. See `CLAUDE.md` for the full
policy.

### Backend tests

Use pytest with `MagicMock` for the Shesha instance and a real topic manager
backed by `tmp_path`:

```python
from unittest.mock import MagicMock
from shesha.experimental.your_tool.dependencies import YourToolState

def test_list_repos(tmp_path):
    shesha = MagicMock()
    shesha.list_projects.return_value = ["proj-1"]
    topic_mgr = YourTopicManager(tmp_path / "topics")
    state = YourToolState(shesha=shesha, topic_mgr=topic_mgr, ...)
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
cd src/shesha/experimental/your_tool/frontend
npm test
```
