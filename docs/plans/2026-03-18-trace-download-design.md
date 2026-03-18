# Trace Download Design

## Goal

Allow users to download the raw JSONL trace file from the TraceViewer panel for debugging purposes.

## Backend

Add a new endpoint to `src/shesha/experimental/shared/routes.py`:

```
GET /api/topics/{name}/trace-download/{trace_id}
```

This URL pattern avoids a route conflict with the existing `get_trace` endpoint, which uses a greedy `{trace_id:path}` converter that would swallow a nested `/download` segment.

Returns the raw JSONL file from disk with:
- `Content-Disposition: attachment; filename="<original-filename>.jsonl"`
- `Content-Type: application/x-ndjson`

The downloaded filename matches the on-disk filename (e.g., `2025-03-18T14-35-42-127_a1b2c3d4.jsonl`).

**Security constraint:** The endpoint must use the same iterate-and-match approach as `get_trace` — iterate all trace files for the topic and match by stem or header `trace_id`. It must never construct a file path directly from the `trace_id` parameter, to prevent path traversal.

## Frontend API Client

Add a `download` method to `sharedApi.traces` in `client.ts` that:
1. Fetches the `/trace-download` endpoint
2. Creates a blob URL from the response
3. Triggers a browser file download via a temporary anchor element

## Frontend UI

Add a download icon button in the `TraceViewer.tsx` panel header bar, next to the close button. Uses a Lucide download icon. Clicking it calls the download method.
