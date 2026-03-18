# Trace Download Design

## Goal

Allow users to download the raw JSONL trace file from the TraceViewer panel for debugging purposes.

## Backend

Add a new endpoint to `src/shesha/experimental/shared/routes.py`:

```
GET /api/topics/{name}/traces/{trace_id}/download
```

Returns the raw JSONL file from disk with:
- `Content-Disposition: attachment; filename="<original-filename>.jsonl"`
- `Content-Type: application/x-ndjson`

Reuses the existing trace-loading logic to locate the file on disk, but streams the raw file instead of parsing it into `TraceFull`.

The downloaded filename matches the on-disk filename (e.g., `2025-03-18T14-35-42-127_a1b2c3d4.jsonl`).

## Frontend API Client

Add a `download` method to `sharedApi.traces` in `client.ts` that:
1. Fetches the `/download` endpoint
2. Creates a blob URL from the response
3. Triggers a browser file download via a temporary anchor element

## Frontend UI

Add a download icon button in the `TraceViewer.tsx` panel header bar, next to the close button. Uses a Lucide download icon. Clicking it calls the download method.
