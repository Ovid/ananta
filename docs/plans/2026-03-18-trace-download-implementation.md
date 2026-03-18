# Trace Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a download button to the TraceViewer panel that downloads the raw JSONL trace file for debugging.

**Architecture:** New backend endpoint (`GET /api/topics/{name}/trace-download/{trace_id}`) serves the raw JSONL file using `FileResponse`. Frontend adds a download method to the shared API client and a download button to the TraceViewer header.

**Tech Stack:** Python/FastAPI (FileResponse), TypeScript/React (blob download)

---

### Task 1: Backend — trace download endpoint

**Files:**
- Modify: `src/shesha/experimental/shared/routes.py`
- Test: `tests/experimental/shared/test_shared_routes.py`

**Step 1: Write the failing test**

Add to `tests/experimental/shared/test_shared_routes.py`:

```python
import json

class TestTraceDownload:
    """The trace-download endpoint returns the raw JSONL file."""

    def _make_trace_file(self, tmp_path: Path, filename: str = "2025-01-15T10-30-00-123_abc12345.jsonl") -> Path:
        trace_file = tmp_path / filename
        header = {
            "type": "header",
            "trace_id": "abc12345",
            "timestamp": "2025-01-15T10:30:00Z",
            "question": "What is abiogenesis?",
            "document_ids": ["doc1"],
            "model": "gpt-5-mini",
            "system_prompt": "You are a helpful assistant",
            "subcall_prompt": "Answer concisely",
        }
        step = {
            "type": "step",
            "step_type": "code_generated",
            "iteration": 0,
            "timestamp": "2025-01-15T10:30:01Z",
            "content": "print('hello')",
            "tokens_used": 150,
            "duration_ms": None,
        }
        summary = {
            "type": "summary",
            "answer": "Abiogenesis is...",
            "total_iterations": 1,
            "total_tokens": {"prompt": 100, "completion": 50},
            "total_duration_ms": 5000,
            "status": "success",
        }
        trace_file.write_text(
            json.dumps(header) + "\n" + json.dumps(step) + "\n" + json.dumps(summary) + "\n"
        )
        return trace_file

    def test_download_returns_raw_jsonl(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        trace_file = self._make_trace_file(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = [trace_file]

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/abc12345")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-ndjson"
        assert "attachment" in resp.headers["content-disposition"]
        assert "2025-01-15T10-30-00-123_abc12345.jsonl" in resp.headers["content-disposition"]
        # Body is the raw file content
        lines = resp.text.strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["type"] == "header"
        assert json.loads(lines[0])["system_prompt"] == "You are a helpful assistant"

    def test_download_matches_by_stem(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        trace_file = self._make_trace_file(tmp_path)
        state.topic_mgr._storage.list_traces.return_value = [trace_file]

        app = _make_app(state)
        client = TestClient(app)
        # Match by filename stem (what the frontend sends as trace_id)
        resp = client.get("/api/topics/my-topic/trace-download/2025-01-15T10-30-00-123_abc12345")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]

    def test_download_not_found(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        state.topic_mgr.resolve.return_value = "proj-1"
        state.topic_mgr._storage.list_traces.return_value = []

        app = _make_app(state)
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/nonexistent")
        assert resp.status_code == 404

    def test_download_uses_custom_callbacks(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        trace_file = self._make_trace_file(tmp_path)

        def custom_resolve(s: object, name: str) -> list[str]:
            return ["custom-proj"]

        def custom_list(s: object, project_id: str) -> list[Path]:
            return [trace_file]

        app = _make_app(
            state,
            resolve_project_ids=custom_resolve,
            list_trace_files=custom_list,
        )
        client = TestClient(app)
        resp = client.get("/api/topics/my-topic/trace-download/abc12345")
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/experimental/shared/test_shared_routes.py::TestTraceDownload -v`
Expected: FAIL — 404 because the route does not exist yet.

**Step 3: Write minimal implementation**

In `src/shesha/experimental/shared/routes.py`:

1. Add `FileResponse` to the existing import from `fastapi.responses`:
   ```python
   from fastapi.responses import FileResponse, PlainTextResponse
   ```

2. Add the download route inside `create_shared_router`, after the existing `get_trace` route (around line 353), before the `# --- History & Export ---` section:

```python
    @router.get("/api/topics/{name}/trace-download/{trace_id}")
    def download_trace(name: str, trace_id: str) -> FileResponse:
        project_ids = _get_project_ids(name)
        for project_id in project_ids:
            trace_files = _get_trace_files(project_id)
            for tf in trace_files:
                parsed = _parse_trace_file(tf)
                header = parsed["header"]
                assert isinstance(header, dict)
                if tf.stem == trace_id or header.get("trace_id") == trace_id:
                    return FileResponse(
                        tf,
                        filename=tf.name,
                        media_type="application/x-ndjson",
                    )
        raise HTTPException(404, f"Trace '{trace_id}' not found")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/experimental/shared/test_shared_routes.py::TestTraceDownload -v`
Expected: PASS (all 4 tests)

**Step 5: Run full test suite for shared routes**

Run: `pytest tests/experimental/shared/test_shared_routes.py -v`
Expected: PASS (all existing tests still pass)

**Step 6: Commit**

```bash
git add src/shesha/experimental/shared/routes.py tests/experimental/shared/test_shared_routes.py
git commit -m "feat: add trace download endpoint"
```

---

### Task 2: Frontend — API client download method

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/api/client.ts`
- Test: `src/shesha/experimental/shared/frontend/src/api/__tests__/client.test.ts`

**Step 1: Write the failing test**

Create `src/shesha/experimental/shared/frontend/src/api/__tests__/client.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('sharedApi.traces.download', () => {
  let clickSpy: ReturnType<typeof vi.fn>
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    clickSpy = vi.fn()
    revokeObjectURLSpy = vi.fn()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:http://localhost/fake'),
      revokeObjectURL: revokeObjectURLSpy,
    })
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickSpy,
    } as unknown as HTMLAnchorElement)
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node)
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches the trace-download endpoint and triggers a file download', async () => {
    const blob = new Blob(['test'], { type: 'application/x-ndjson' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({
        'content-disposition': 'attachment; filename="trace.jsonl"',
      }),
      blob: () => Promise.resolve(blob),
    }))

    const { sharedApi } = await import('../client')
    await sharedApi.traces.download('my-topic', 'trace-123')

    expect(fetch).toHaveBeenCalledWith('/api/topics/my-topic/trace-download/trace-123')
    expect(clickSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:http://localhost/fake')
  })

  it('throws on non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
    }))

    const { sharedApi } = await import('../client')
    await expect(sharedApi.traces.download('t', 'x')).rejects.toThrow('Not Found')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/api/__tests__/client.test.ts`
Expected: FAIL — `sharedApi.traces.download` is not a function.

**Step 3: Write minimal implementation**

In `src/shesha/experimental/shared/frontend/src/api/client.ts`, add `download` to the `traces` object:

```typescript
  traces: {
    list: (topic: string) => request<TraceListItem[]>(
      `/topics/${encodeURIComponent(topic)}/traces`,
    ),
    get: (topic: string, traceId: string) => request<TraceFull>(
      `/topics/${encodeURIComponent(topic)}/traces/${encodeURIComponent(traceId)}`,
    ),
    download: async (topic: string, traceId: string) => {
      const resp = await fetch(`${BASE}/topics/${encodeURIComponent(topic)}/trace-download/${encodeURIComponent(traceId)}`)
      if (!resp.ok) throw new Error(resp.statusText)
      const blob = await resp.blob()
      const disposition = resp.headers.get('content-disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `${traceId}.jsonl`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
  },
```

**Step 4: Run test to verify it passes**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/api/__tests__/client.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/api/client.ts src/shesha/experimental/shared/frontend/src/api/__tests__/client.test.ts
git commit -m "feat: add trace download method to shared API client"
```

---

### Task 3: Frontend — download button in TraceViewer

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/TraceViewer.tsx`
- Test: `src/shesha/experimental/shared/frontend/src/components/__tests__/TraceViewer.test.tsx`

**Step 1: Write the failing test**

Add to `src/shesha/experimental/shared/frontend/src/components/__tests__/TraceViewer.test.tsx`:

```typescript
describe('TraceViewer download button', () => {
  it('renders a download button in the header', async () => {
    const fetchTrace = vi.fn().mockResolvedValue(mockTrace)
    const downloadTrace = vi.fn()

    await act(async () => {
      render(
        <TraceViewer
          topicName="test"
          traceId="t-1"
          onClose={vi.fn()}
          fetchTrace={fetchTrace}
          downloadTrace={downloadTrace}
        />
      )
    })

    await screen.findByText(/test-model/)
    const btn = screen.getByRole('button', { name: /download/i })
    expect(btn).toBeTruthy()
  })

  it('calls downloadTrace with topicName and traceId on click', async () => {
    const user = userEvent.setup()
    const fetchTrace = vi.fn().mockResolvedValue(mockTrace)
    const downloadTrace = vi.fn()

    await act(async () => {
      render(
        <TraceViewer
          topicName="test"
          traceId="t-1"
          onClose={vi.fn()}
          fetchTrace={fetchTrace}
          downloadTrace={downloadTrace}
        />
      )
    })

    await screen.findByText(/test-model/)
    const btn = screen.getByRole('button', { name: /download/i })
    await user.click(btn)
    expect(downloadTrace).toHaveBeenCalledWith('test', 't-1')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TraceViewer.test.tsx`
Expected: FAIL — `downloadTrace` is not a recognized prop / download button not found.

**Step 3: Write minimal implementation**

In `src/shesha/experimental/shared/frontend/src/components/TraceViewer.tsx`:

1. Add `downloadTrace` to the props interface:

```typescript
interface TraceViewerProps {
  topicName: string
  traceId: string
  onClose: () => void
  fetchTrace: (topicName: string, traceId: string) => Promise<TraceFull>
  downloadTrace: (topicName: string, traceId: string) => void
}
```

2. Update the component signature to destructure the new prop:

```typescript
export default function TraceViewer({ topicName, traceId, onClose, fetchTrace, downloadTrace }: TraceViewerProps) {
```

3. Add a download button in the header div, next to the close button. Replace the header `div`:

```tsx
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">Trace Viewer</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadTrace(topicName, traceId)}
            className="text-text-dim hover:text-text-secondary text-sm"
            aria-label="Download trace"
            title="Download trace"
          >
            ↓
          </button>
          <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg">&times;</button>
        </div>
      </div>
```

**Step 4: Run test to verify it passes**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TraceViewer.test.tsx`
Expected: PASS

**Step 5: Fix existing tests**

The existing TraceViewer tests don't pass `downloadTrace`. Add `downloadTrace={vi.fn()}` to every existing `<TraceViewer ... />` render call in the test file to satisfy the new required prop.

**Step 6: Run all TraceViewer tests**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/TraceViewer.test.tsx`
Expected: PASS (all tests)

**Step 7: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/TraceViewer.tsx src/shesha/experimental/shared/frontend/src/components/__tests__/TraceViewer.test.tsx
git commit -m "feat: add download button to TraceViewer"
```

---

### Task 4: Wire up TraceViewer download prop in all explorers

**Files:**
- Modify: Each explorer's `App.tsx` that renders `<TraceViewer>`

Find all `App.tsx` files that render `<TraceViewer>` and pass the `downloadTrace` prop using `sharedApi.traces.download` (or the explorer's own API wrapper if it extends the shared one). Each explorer renders TraceViewer like:

```tsx
{traceView && (
  <TraceViewer
    topicName={traceView.topic}
    traceId={traceView.traceId}
    onClose={() => setTraceView(null)}
    fetchTrace={api.traces.get}
    downloadTrace={api.traces.download}   // ← add this line
  />
)}
```

**Step 1: Find all TraceViewer usages**

Run: `grep -rn "TraceViewer" src/shesha/experimental/*/frontend/src/ --include="*.tsx" -l`

**Step 2: Add `downloadTrace={api.traces.download}` to each TraceViewer render**

For each file found, add the prop. The `api` object should already include `sharedApi.traces` or extend it.

**Step 3: Run frontend type-check for all explorers**

Run: `cd src/shesha/experimental/shared/frontend && npx tsc --noEmit`

Repeat for each explorer's frontend directory. Expected: no type errors.

**Step 4: Commit**

```bash
git add src/shesha/experimental/*/frontend/src/App.tsx
git commit -m "feat: wire up trace download in all explorers"
```

---

### Task 5: Type-check, lint, and full test pass

**Step 1: Run Python tests and checks**

Run: `make all`
Expected: PASS

**Step 2: Run frontend tests for shared**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run`
Expected: PASS

**Step 3: Run frontend type-check**

Run: `cd src/shesha/experimental/shared/frontend && npx tsc --noEmit`
Expected: PASS

**Step 4: Commit if any fixes were needed**

```bash
git commit -m "fix: address lint/type issues from trace download"
```
