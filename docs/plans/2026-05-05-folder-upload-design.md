# Folder Upload (Document Explorer) — Design

## Problem

The Document Explorer's drop zone accepts files but not folders. Users with a folder of research material must select files manually, which is tedious and error-prone for collections with subfolders.

Two pressures shape the design:

1. **Folders are noisy.** Real folders contain dotfiles (`.git`, `.DS_Store`, `.env`), tooling cruft (`node_modules`, `__pycache__`, `.venv`), and files outside the supported-extension allowlist. Naive recursion would waste storage and risks indexing secrets.
2. **Folders can be large.** A research project may have 200+ PDFs across nested subdirs, exceeding the current 200 MB single-request cap. Pathological cases (a backup folder, `~/Documents`) could have tens of thousands of files.

## Goal

Drop a folder onto the explorer, get its supported documents added to the currently selected topic, with sensible bounds on how much can be uploaded at once.

Out of scope for v1 (tracked in TODO.md):
- Sensitive-info filtering (skipping `.env`, `.py`, dotfiles, cruft directories like `node_modules`)
- All-or-nothing rollback across batches
- Auto-creating a topic from the folder name

Out of scope entirely: nested topics (would require a topic-hierarchy redesign), `.gitignore` honoring, content-based deduplication, resumable uploads.

## User-facing flow

**Precondition:** A topic must be selected. If no topic is active, the drop zone is disabled (visually grayed, with a "Select a topic first" hover hint) and a folder drop is rejected before the walk starts.

1. **Drop folder.** Frontend detects directory entries via `DataTransferItem.webkitGetAsEntry()` and walks them asynchronously.
2. **Walk + filter.** Recurse through every directory (no cruft pruning in v1; deferred per TODO.md). Files matching the supported-extension allowlist are queued for upload; files larger than 50 MB are recorded as "skipped: file exceeds 50 MB limit"; files outside the allowlist are recorded as "skipped: unsupported extension." A simple "Scanning…" indicator renders on the drop zone during the walk (no per-file count — see config note below; with the 500-file cap, walks complete quickly enough that an incrementing count adds no real value).
3. **Hard cap during walk.** If post-filter file count exceeds 500, bail early and refuse: "More than 500 files after filtering — folder is too large for upload."
4. **Pre-flight modal.** Once the walk finishes, show:
   - Target topic: the currently active topic (read-only label — "Add 47 files to: Downloads")
   - Files to upload, total bytes
   - Files to skip, grouped by reason (in v1: only "unsupported extension" and "exceeds 50 MB file limit")
   - Soft warning above 100 files: "This will add 230 files. Continue?"
   - Buttons: **Continue / Show details / Cancel**
5. **Chunked upload.** On Continue, the frontend partitions the file list into batches with a target size of 50 MB each (server cap is 200 MB; smaller target gives finer progress and faster cancel). Batches POST sequentially to the existing `/api/documents/upload` endpoint. The same modal switches to a progress view: single overall bar, "Uploading 73 of 312 files… (batch 4 of 18)", with a **Cancel** button enabled between batches (cancel waits for the current batch to finish, then halts).
6. **Post-upload summary.** Same modal switches to summary view: per-file rows grouped as ingested / failed / skipped, with reasons attached to failed and skipped rows.

## Architectural decisions

### Topic targeting

- Folder upload always targets the **currently selected topic**. No topic is created from the folder name.
- The pre-flight modal shows the target topic as a read-only label so the user can confirm before clicking Continue.
- If no topic is selected, the drop zone is disabled and folder drops are rejected before the walk starts.
- Auto-creating a topic from the folder name is deferred to a future iteration (see TODO.md). If the user wants a fresh topic for a folder's contents, they create the topic first, select it, then drop.

### Path representation

- Add a new `relative_path: str | None` field to `DocumentInfo` and `meta.json`.
- For folder uploads, the value is the path relative to the dropped folder's root (e.g., `docs/api/v2/README.md`). The leaf filename remains the document's `filename` (`README.md`).
- For single-file uploads, `relative_path` is `null`. Existing single-file flow is unchanged.
- The frontend renders `relative_path` as a subtitle under the filename in the topic's document list, so two `README.md` files in different subdirs are visually disambiguated.
- The RLM-side document object exposes `relative_path` via `ParsedDocument.metadata["relative_path"]` so the LLM can filter by path if it chooses (e.g., "only consider files under `docs/`").
- **Project-id collision** is still handled by the existing 8-char hash in `_slugify(stem) + hash` — no change needed there.

### Filtering policy

Frontend walks every directory in v1 (no cruft pruning, no dot-dir pruning). The only filter is the existing supported-extension allowlist, mirrored client-side to avoid round-trip 422s on every unsupported file.

- Files with extensions outside the allowlist are recorded as "skipped: unsupported extension" and surface in the summary modal.
- Dotfiles, dot-dirs, cruft directories (`node_modules`, etc.), and types known to often hold secrets (`.env`, `.py`) are **not** filtered. They flow through to the backend if their extension is on the allowlist.

This is a deliberately weaker stance than the original brainstorm. Implications:

- A typical project folder containing `node_modules/` will hit the 500-file cap during the walk and be refused, forcing the user to drop a focused subdirectory. This is acceptable v1 behavior.
- A folder containing `.env` will upload it to the topic. **Users worried about secret exposure should not drop folders containing `.env` files.** A v2 filter is tracked in TODO.md.

The backend allowlist remains the only enforced boundary.

### Size handling

- Per-file cap: 50 MB (unchanged, enforced server-side).
- Per-batch cap: 200 MB (unchanged, enforced server-side).
- **Client-side chunking with a 50 MB target.** Frontend partitions the filtered file list into batches that aim for 50 MB each (well under the 200 MB server cap). Smaller batches give finer progress granularity and faster cancel response. The 200 MB cap is structurally unreachable given the 50 MB per-file cap and 50 MB target chunk size, so the partitioner does not separately enforce it.
- Files larger than 50 MB are recorded as skipped at pre-flight time with reason "file exceeds 50 MB limit"; the backend per-file failure path is a fallback if the frontend ever drifts.

### Configuration

All upload-related limits live in a single Python module `src/ananta/explorers/document/config.py`:

- `MAX_UPLOAD_BYTES` — per-file cap (50 MB)
- `MAX_AGGREGATE_UPLOAD_BYTES` — per-batch cap (200 MB)
- `MAX_FOLDER_FILES` — folder-walk early-bail cap (500)
- `SOFT_WARN_FOLDER_FILES` — pre-flight soft warning threshold (100)
- `TARGET_BATCH_BYTES` — chunked-upload target size (50 MB)

Backend imports from this module. The frontend mirrors the values inline in `folder-walk.ts` with a comment pointing at the backend file as the source of truth. (Runtime configurability via env vars or a settings file is out of scope for v1; the constants module is the seam to add it later.)

### Failure handling

Failures are handled at two granularities.

**Per-file (within a batch).** The upload route currently raises `HTTPException(422)` and rolls back the entire batch on any single-file failure (unsupported extension, extraction failure, oversized). This design changes that to per-file partial success:

- Each file is wrapped in its own try/except inside the route.
- On per-file failure, that file's partial state (upload dir, project) is rolled back; other files in the same batch still commit.
- The response shape changes: each `DocumentUploadResponse` row carries `status: "created" | "failed"` and an optional `reason` field.
- This is a behavior change for **all** multi-file uploads, not just folder upload. Single-file uploads are unaffected (a one-file batch has identical observable behavior either way).

**Per-batch (across batches).** Best-effort:

- A batch-level failure (network error, 500 from the server, 413 if size estimation was off) halts the upload. Batches already committed stay. Summary modal reports the partial success.
- A `upload_session_id` (UUID) is generated per folder upload and stored in each project's `meta.json`. Unused today; keeps the door open for a future cleanup endpoint without a migration.
- TODO.md tracks the all-or-nothing limitation.

### Cancel

- During walk: instant (kill the recursion).
- During upload: enabled between batches. Clicking cancel during an in-flight batch waits for that batch to finish, then halts. Avoids needing to reason about how the backend handles a client-aborted multipart request.

## Data flow

```
Drop event (only enabled if a topic is selected)
   │
   ▼
Async walk (DataTransferItem.webkitGetAsEntry)
   │  ├─ recurse all directories (no pruning in v1)
   │  ├─ allowlist-match files; non-matches recorded as skipped
   │  ├─ early-bail at 500 post-filter files
   │  └─ stream "Scanning… N files" to UI
   ▼
Pre-flight modal (target topic label, counts, skipped reasons, Continue/Cancel)
   │
   ▼
Generate UUID upload_session_id
   │
   ▼
Partition into batches targeting 50 MB
   │
   ▼
For each batch: POST /api/documents/upload
   │  multipart: files[], topic, upload_session_id, relative_path[]
   │  backend per-file try/except → partial-success response
   │  meta.json carries relative_path + upload_session_id
   │
   ▼
Summary modal (ingested / failed / skipped, per-file reasons)
```

## Backend changes

- New `config.py`: holds `MAX_UPLOAD_BYTES`, `MAX_AGGREGATE_UPLOAD_BYTES`, `MAX_FOLDER_FILES`, `SOFT_WARN_FOLDER_FILES`, `TARGET_BATCH_BYTES`. `api.py` imports from here; existing module-level constants in `api.py` are removed.
- `schemas.py`:
  - Add `relative_path: str | None` and `upload_session_id: str | None` to `DocumentInfo` and the upload form.
  - Add `status: Literal["created", "failed"]` and `reason: str | None` to `DocumentUploadResponse`.
- `api.py` (`POST /api/documents/upload`):
  - Wrap the existing per-file work in a try/except. On per-file failure, roll back that file's partial state only and append a `status="failed"` row with the reason; continue with the next file.
  - Accept and persist `relative_path` and `upload_session_id` in `meta.json`.
  - Include `relative_path` in the `ParsedDocument.metadata` dict so the RLM-side document object exposes it.
  - Topic creation: keep current behavior (route still calls `state.topic_mgr.create(topic)` when `topic` is provided). Folder upload always sends the *currently selected* topic name, so this resolves to a no-op or accept-existing in practice — no change needed if `create()` is idempotent on existing names. Verify during implementation.
- No new endpoints. No changes to `extractors.py` or `websockets.py`.

## Frontend changes

- `UploadArea.tsx`:
  - Disable the drop zone (and `<input type="file">`) when no topic is selected; show a "Select a topic first" hint.
  - Detect directory entries on drop, walk via `webkitGetAsEntry`, show a simple "Scanning…" indicator during the walk.
  - Add a separate "Upload folder" button beside the existing file upload, using a second `<input type="file" webkitdirectory>` (a single input cannot be both `multiple` and `webkitdirectory`). The click path converts the resulting `FileList` (whose entries carry `webkitRelativePath`) into the same `WalkedFile[]` shape as the drop path.
- New `FolderUploadModal.tsx`: pre-flight → progress → summary states. Pre-flight shows the active topic name as a read-only label.
- New `folder-walk.ts` utility: async recursion (no pruning in v1), supported-extension and oversize match, early-bail at the configured cap, target-byte batch partitioning. Constants mirror `config.py` with a comment pointing at the backend file as the source of truth.
- `App.tsx` / API client: support multi-batch upload orchestration; pass `relative_path`, `upload_session_id`, and the active topic in each batch; aggregate per-file `status="failed"` rows into the summary view.
- Document list rendering: show `relative_path` as a subtitle when present.

## Testing

Per CLAUDE.md, all code is TDD.

Frontend (vitest):
- Walk records non-allowlist files as skipped with reason "unsupported extension".
- Walk records oversized (>50 MB) files as skipped with reason "file exceeds 50 MB limit".
- Walk early-bails at the configured `MAX_FOLDER_FILES` (500).
- Drop is disabled when no topic is selected.
- Soft warning fires above `SOFT_WARN_FOLDER_FILES` (100).
- Batch partitioner aims for `TARGET_BATCH_BYTES` (50 MB).
- Cancel-between-batches halts after current batch.
- Summary modal renders ingested / failed / skipped rows with reasons.
- Click-to-upload-folder via `<input type="file" webkitdirectory>` produces the same `WalkedFile[]` as the drop path.

Backend (pytest):
- `relative_path` round-trips through upload → `meta.json` → API response.
- `upload_session_id` round-trips identically.
- Single-file upload (no `relative_path`) still works.
- Multi-file upload: one bad file in a batch returns `status="failed"` with a reason for that file; other files still commit with `status="created"`.
- Multi-file upload: oversized file returns `status="failed"` for that file only.

Manual verification: drop a folder of mixed PDFs / Markdown into a selected topic; confirm pre-flight, progress, and summary all behave as designed. Drop a `node_modules`-heavy folder to confirm the 500-file cap rejects it cleanly.

## Risks and open issues

- **Browser variation in directory APIs.** `webkitGetAsEntry` is broadly supported but some edge cases differ across browsers. The plan handles known quirks (e.g., `readEntries` returning incomplete batches) defensively. Cross-browser smoke testing is not a hard prerequisite for v1.
- **All-or-nothing batch rollback deferred.** Tracked in TODO.md.
- **Sensitive-info filter deferred.** Tracked in TODO.md. Until that's built, users dropping folders containing `.env`, `.py`, or other secret-bearing files will have those uploaded to the topic. Documented in the filtering policy section above so users can make informed choices.
- **Multi-file partial-success is a behavior change.** Existing API consumers who rely on a multi-file upload being all-or-nothing (uncommon — there's no other consumer of `/api/documents/upload` than this frontend) would see the new partial-success response shape. Worth a note in CHANGELOG under Changed.
