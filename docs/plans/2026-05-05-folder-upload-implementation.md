# Folder Upload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Drop a folder onto the Document Explorer and have its supported documents added (recursively) to the currently selected topic, with a pre-flight modal, chunked upload, and per-file partial-success reporting.

**Architecture:** Frontend walks the dropped directory tree via `DataTransferItem.webkitGetAsEntry` (drag) or `<input type="file" webkitdirectory>` (click), applies the supported-extension allowlist plus an oversize check, partitions matched files into ~50 MB batches, and POSTs them sequentially to the existing `/api/documents/upload` endpoint. The endpoint is changed to per-file partial success so one bad file doesn't fail an entire batch. New `relative_path` metadata preserves folder structure for display *and* is exposed to the RLM via `ParsedDocument.metadata`. Drop is disabled when no topic is selected. All upload limits live in a single `config.py`. See design at `docs/plans/2026-05-05-folder-upload-design.md`.

**Tech Stack:** FastAPI, Pydantic, pytest (backend); React, TypeScript, Vite, vitest (frontend).

**Conventions:**
- TDD per CLAUDE.md: red → green → refactor → commit on every task.
- Backend tests live under `tests/unit/explorers/document/`.
- Frontend tests live under `src/ananta/explorers/document/frontend/src/components/__tests__/`.
- Run `make all` after each phase before moving on.
- Each task ends with a commit. Don't combine tasks into one commit.

**Requirements traceability:** Each task header lists which design point it addresses, mapped against `docs/plans/2026-05-05-folder-upload-design.md`.

---

## Phase A — Backend

### Task A0: Centralize upload limits in `config.py`

**Requirement:** design "Configuration" section.

**Files:**
- Create: `src/ananta/explorers/document/config.py`
- Modify: `src/ananta/explorers/document/api.py` (remove inline constants, import from config)
- Test: `tests/unit/explorers/document/test_config.py`

#### RED

Write a test that imports the new constants and asserts their values. This catches accidental changes during refactor.

```python
# tests/unit/explorers/document/test_config.py
from ananta.explorers.document import config


def test_upload_limits_have_expected_values():
    assert config.MAX_UPLOAD_BYTES == 50 * 1024 * 1024
    assert config.MAX_AGGREGATE_UPLOAD_BYTES == 200 * 1024 * 1024
    assert config.MAX_FOLDER_FILES == 500
    assert config.SOFT_WARN_FOLDER_FILES == 100
    assert config.TARGET_BATCH_BYTES == 50 * 1024 * 1024
```

Run: `pytest tests/unit/explorers/document/test_config.py -v`
Expected failure: `ModuleNotFoundError: ananta.explorers.document.config`.
If it passes unexpectedly: someone already created the module — verify its contents match the design.

#### GREEN

Create the config module:

```python
# src/ananta/explorers/document/config.py
"""Centralized upload limits for the Document Explorer.

Single source of truth for upload-related caps. The frontend mirrors these
values inline in folder-walk.ts; keep them in sync.
"""

from __future__ import annotations

# Per-file upload cap (50 MB). Enforced server-side; mirrored on frontend
# pre-flight to skip oversized files before sending.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Per-batch (single multipart request) cap (200 MB). Enforced server-side.
MAX_AGGREGATE_UPLOAD_BYTES = 200 * 1024 * 1024

# Folder-walk early-bail cap. After this many post-allowlist-match files,
# the walk refuses with "folder too large".
MAX_FOLDER_FILES = 500

# Pre-flight soft-warning threshold. Modal asks the user to confirm above this.
SOFT_WARN_FOLDER_FILES = 100

# Target chunked-upload batch size. Frontend partitions to keep batches near
# this; well under MAX_AGGREGATE_UPLOAD_BYTES.
TARGET_BATCH_BYTES = 50 * 1024 * 1024
```

Update `src/ananta/explorers/document/api.py`:

```python
# Replace the existing two constants near the top:
#   MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#   MAX_AGGREGATE_UPLOAD_BYTES = 200 * 1024 * 1024
# With an import:
from ananta.explorers.document.config import (
    MAX_AGGREGATE_UPLOAD_BYTES,
    MAX_UPLOAD_BYTES,
)
```

Run: `pytest tests/unit/explorers/document/ -v`
Expected: PASS (new test plus all existing).

#### REFACTOR

- Look for any other module under `src/ananta/explorers/document/` that hard-codes these byte values. `grep -rn '50 \* 1024 \* 1024\|200 \* 1024 \* 1024' src/ananta/explorers/document/` — replace any duplicates with imports from `config`.
- Confirm the docstring on `config.py` reads cleanly (no "TODO" or stale references).
- No anticipatory env-var/settings hooks — those are deferred per design.

#### Commit

```bash
git add src/ananta/explorers/document/config.py \
        src/ananta/explorers/document/api.py \
        tests/unit/explorers/document/test_config.py
git commit -m "refactor: centralize document-explorer upload limits in config.py"
```

---

### Task A1: Add `relative_path` and `upload_session_id` to `DocumentInfo`

**Requirement:** design "Path representation" + "Backend changes" — schemas.

**Files:**
- Modify: `src/ananta/explorers/document/schemas.py`
- Modify: `src/ananta/explorers/document/api.py` (`_build_doc_info`)
- Test: `tests/unit/explorers/document/test_schemas.py`

#### RED

Write a test that builds a `DocumentInfo` with the two new optional fields, and another that omits them.

```python
def test_document_info_accepts_relative_path_and_session_id():
    info = DocumentInfo(
        project_id="x-12345678",
        filename="README.md",
        content_type="text/markdown",
        size=42,
        upload_date="2026-05-05T00:00:00Z",
        page_count=None,
        relative_path="docs/api/README.md",
        upload_session_id="11111111-1111-1111-1111-111111111111",
    )
    assert info.relative_path == "docs/api/README.md"
    assert info.upload_session_id == "11111111-1111-1111-1111-111111111111"


def test_document_info_relative_path_optional():
    info = DocumentInfo(
        project_id="x-12345678",
        filename="README.md",
        content_type="text/markdown",
        size=42,
        upload_date="2026-05-05T00:00:00Z",
        page_count=None,
    )
    assert info.relative_path is None
    assert info.upload_session_id is None
```

Run: `pytest tests/unit/explorers/document/test_schemas.py -v -k relative_path`
Expected failure: `pydantic.ValidationError` — fields not allowed.
If it passes unexpectedly: schema already updated; check `_build_doc_info` instead.

#### GREEN

Update `DocumentInfo` in `schemas.py`:

```python
class DocumentInfo(BaseModel):
    project_id: str
    filename: str
    content_type: str
    size: int
    upload_date: str
    page_count: int | None
    relative_path: str | None = None
    upload_session_id: str | None = None
```

Update `_build_doc_info` in `api.py` to populate the two new fields from `meta`:

```python
return DocumentInfo(
    project_id=project_id,
    filename=meta.get("filename", ""),
    content_type=meta.get("content_type", ""),
    size=meta.get("size", 0),
    upload_date=meta.get("upload_date", ""),
    page_count=meta.get("page_count"),
    relative_path=meta.get("relative_path"),
    upload_session_id=meta.get("upload_session_id"),
)
```

Run: `pytest tests/unit/explorers/document/test_schemas.py tests/unit/explorers/document/test_api.py -v`
Expected: PASS.

#### REFACTOR

- Look for other places that construct `DocumentInfo` (`grep -rn "DocumentInfo(" src/ananta/explorers/document/`). Make sure none of them pass positional args that now collide with the new optional fields. Pydantic model construction is keyword-based here, so this is just a sanity check.
- No new abstractions; the two fields are direct mirrors of `meta.json` keys.

#### Commit

```bash
git add src/ananta/explorers/document/schemas.py \
        src/ananta/explorers/document/api.py \
        tests/unit/explorers/document/test_schemas.py
git commit -m "feat: add relative_path and upload_session_id to DocumentInfo"
```

---

### Task A2: Persist `relative_path` and `upload_session_id` from upload form

**Requirement:** design "Path representation" + "Failure handling" — meta.json fields.

**Files:**
- Modify: `src/ananta/explorers/document/api.py` (`upload_documents` signature + meta dict)
- Test: `tests/unit/explorers/document/test_api.py`

#### RED

Add to `TestUploadEndpoint` (or wherever upload tests live):

```python
def test_upload_persists_relative_path_and_session_id(
    self,
    client,
    uploads_dir: Path,
):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("README.md", b"hello", "text/markdown"))],
        data={
            "relative_path": "docs/api/README.md",
            "upload_session_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert response.status_code == 200
    [doc] = response.json()
    project_id = doc["project_id"]

    meta = json.loads((uploads_dir / project_id / "meta.json").read_text())
    assert meta["relative_path"] == "docs/api/README.md"
    assert meta["upload_session_id"] == "11111111-1111-1111-1111-111111111111"
```

Run: `pytest tests/unit/explorers/document/test_api.py -v -k relative_path`
Expected failure: form fields are ignored; meta.json lacks those keys.
If it passes unexpectedly: someone already added them — re-check the per-file partial-success change is still pending for A4.

#### GREEN

Update `upload_documents`:

```python
@router.post("/documents/upload")
async def upload_documents(
    files: list[UploadFile],
    topic: str | None = Form(default=None),
    relative_path: list[str] | None = Form(default=None),
    upload_session_id: str | None = Form(default=None),
) -> list[DocumentUploadResponse]:
    ...
```

Inside the per-file loop, pair `relative_path` to the file by index, and add the two fields to the `meta` dict:

```python
for idx, file in enumerate(files):
    ...
    rel_path = (
        relative_path[idx]
        if relative_path is not None and idx < len(relative_path)
        else None
    )
    ...
    meta = {
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "upload_date": datetime.now(UTC).isoformat(),
        "page_count": page_count,
        "relative_path": rel_path,
        "upload_session_id": upload_session_id,
    }
```

`relative_path` is a **repeated** form field (one per file, by index). `upload_session_id` is a single value for the whole batch.

Run: `pytest tests/unit/explorers/document/test_api.py -v`
Expected: new test PASS, existing tests still PASS.

#### REFACTOR

- The pairing-by-index pattern (`relative_path[idx] if ...`) will appear again in A4 inside the wider per-file loop. Don't pre-extract it into a helper now — wait until A4 to see whether a helper actually improves readability.
- Check that the FastAPI `Form` typing for the repeated field doesn't break any client. Run all explorer tests: `pytest tests/unit/explorers/document/ -v`.

#### Commit

```bash
git add src/ananta/explorers/document/api.py \
        tests/unit/explorers/document/test_api.py
git commit -m "feat: persist relative_path and upload_session_id in upload metadata"
```

---

### Task A3: Add `status` and `reason` to `DocumentUploadResponse`

**Requirement:** design "Failure handling" — response shape.

**Files:**
- Modify: `src/ananta/explorers/document/schemas.py`
- Test: `tests/unit/explorers/document/test_schemas.py`

#### RED

```python
def test_document_upload_response_status_and_reason():
    ok = DocumentUploadResponse(
        project_id="x-12345678",
        filename="a.md",
        status="created",
    )
    assert ok.reason is None

    failed = DocumentUploadResponse(
        project_id="",
        filename="bad.pdf",
        status="failed",
        reason="text extraction failed: corrupt PDF",
    )
    assert failed.status == "failed"
    assert failed.reason == "text extraction failed: corrupt PDF"
```

Run: `pytest tests/unit/explorers/document/test_schemas.py -v -k status_and_reason`
Expected failure: `reason` not a recognized field.

#### GREEN

```python
class DocumentUploadResponse(BaseModel):
    project_id: str
    filename: str
    status: str
    reason: str | None = None
```

Run: `pytest tests/unit/explorers/document/test_schemas.py -v`
Expected: PASS.

#### REFACTOR

- Consider tightening `status` to `Literal["created", "failed"]` for stronger typing. Apply only if it doesn't break any existing test (some tests may pass arbitrary status strings); revert if so.
- Run the full test module: `pytest tests/unit/explorers/document/ -v`.

#### Commit

```bash
git add src/ananta/explorers/document/schemas.py \
        tests/unit/explorers/document/test_schemas.py
git commit -m "feat: add status and reason to DocumentUploadResponse"
```

---

### Task A4: Per-file partial success in upload route

**Requirement:** design "Failure handling — per-file" — biggest backend change.

**Files:**
- Modify: `src/ananta/explorers/document/api.py` (`upload_documents`)
- Modify: `tests/unit/explorers/document/test_api.py` (new tests + update existing `test_upload_unsupported_type_returns_422_with_detail`)

#### RED

Add new tests:

```python
def test_upload_partial_success_unsupported_extension(
    self,
    client,
    uploads_dir: Path,
):
    """One unsupported file should NOT fail the whole batch."""
    response = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("good.md", b"hello", "text/markdown")),
            ("files", ("bad.xyz", b"junk", "application/octet-stream")),
            ("files", ("also-good.txt", b"world", "text/plain")),
        ],
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    by_filename = {r["filename"]: r for r in rows}
    assert by_filename["good.md"]["status"] == "created"
    assert by_filename["also-good.txt"]["status"] == "created"
    assert by_filename["bad.xyz"]["status"] == "failed"
    assert "unsupported" in by_filename["bad.xyz"]["reason"].lower()

    good_id = by_filename["good.md"]["project_id"]
    assert (uploads_dir / good_id / "meta.json").exists()


def test_upload_partial_success_oversized(
    self,
    client,
    uploads_dir: Path,
):
    big = b"x" * (51 * 1024 * 1024)
    response = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("good.md", b"hello", "text/markdown")),
            ("files", ("big.md", big, "text/markdown")),
        ],
    )
    assert response.status_code == 200
    rows = response.json()
    by_filename = {r["filename"]: r for r in rows}
    assert by_filename["good.md"]["status"] == "created"
    assert by_filename["big.md"]["status"] == "failed"
    assert "limit" in by_filename["big.md"]["reason"].lower()
```

Update `test_upload_unsupported_type_returns_422_with_detail`. Re-read the existing test before editing. Its intent is "unsupported types are rejected with a useful message." After A4, this becomes "unsupported types appear as failed rows in a 200 response." Rename and rewrite:

```python
def test_upload_unsupported_type_returns_failed_row(self, client, uploads_dir: Path):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("foo.xyz", b"junk", "application/octet-stream"))],
    )
    assert response.status_code == 200
    [row] = response.json()
    assert row["status"] == "failed"
    assert ".xyz" in row["reason"] or "unsupported" in row["reason"].lower()
```

Run: `pytest tests/unit/explorers/document/test_api.py -v`
Expected failure: new tests fail (current behavior is HTTP 422 batch rollback); the rewritten test fails because the route still returns 422.

#### GREEN

Replace the body of `upload_documents` with per-file try/except. Topic-validation up-front is preserved (still all-or-nothing on bad topic name — that's not a per-file concern).

```python
@router.post("/documents/upload")
async def upload_documents(
    files: list[UploadFile],
    topic: str | None = Form(default=None),
    relative_path: list[str] | None = Form(default=None),
    upload_session_id: str | None = Form(default=None),
) -> list[DocumentUploadResponse]:
    if topic:
        try:
            state.topic_mgr.create(topic)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    results: list[DocumentUploadResponse] = []
    total_bytes = 0

    for idx, file in enumerate(files):
        if not file.filename:
            continue

        rel_path = (
            relative_path[idx]
            if relative_path is not None and idx < len(relative_path)
            else None
        )

        upload_dir: Path | None = None
        project_id: str | None = None
        try:
            ext = Path(file.filename).suffix.lower()
            if not is_supported_extension(file.filename):
                results.append(_failed_row(
                    file.filename, f"unsupported file type: {ext}"
                ))
                continue

            content = await file.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                results.append(_failed_row(
                    file.filename,
                    f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                ))
                continue

            total_bytes += len(content)
            if total_bytes > MAX_AGGREGATE_UPLOAD_BYTES:
                # Aggregate cap remains a hard 413 — frontend chunking should
                # ensure this is never reached in practice.
                raise HTTPException(
                    413,
                    f"Total upload size exceeds the "
                    f"{MAX_AGGREGATE_UPLOAD_BYTES // (1024 * 1024)} MB aggregate limit",
                )

            project_id = _make_project_id(file.filename)
            upload_dir = state.uploads_dir / project_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            original_path = upload_dir / f"original{ext}"
            original_path.write_bytes(content)

            try:
                text = extract_text(original_path)
            except ValueError as exc:
                shutil.rmtree(upload_dir, ignore_errors=True)
                results.append(_failed_row(
                    file.filename, f"text extraction failed: {exc}"
                ))
                continue

            page_count = get_page_count(original_path)
            meta = {
                "filename": file.filename,
                "content_type": file.content_type or "application/octet-stream",
                "size": len(content),
                "upload_date": datetime.now(UTC).isoformat(),
                "page_count": page_count,
                "relative_path": rel_path,
                "upload_session_id": upload_session_id,
            }
            (upload_dir / "meta.json").write_text(json.dumps(meta, indent=2))

            state.ananta.create_project(project_id)
            doc = ParsedDocument(
                name=file.filename,
                content=text,
                format=ext.lstrip(".") or "txt",
                metadata={"filename": file.filename, "size": len(content)},
                char_count=len(text),
            )
            state.ananta.storage.store_document(project_id, doc)

            if topic:
                state.topic_mgr.add_item(topic, project_id)

            results.append(DocumentUploadResponse(
                project_id=project_id,
                filename=file.filename,
                status="created",
            ))
        except HTTPException:
            raise  # 413 aggregate cap propagates as before
        except Exception as exc:
            if upload_dir is not None:
                shutil.rmtree(upload_dir, ignore_errors=True)
            if project_id is not None:
                try:
                    state.topic_mgr.remove_item_from_all(project_id)
                except Exception:
                    pass  # Best-effort cleanup
                try:
                    state.ananta.delete_project(project_id)
                except Exception:
                    pass  # Best-effort cleanup
            results.append(_failed_row(file.filename, f"unexpected error: {exc}"))

    return results


def _failed_row(filename: str, reason: str) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        project_id="",
        filename=filename,
        status="failed",
        reason=reason,
    )
```

The whole-request `try / except` rollback is gone — per-file rollback is local now.

Run: `pytest tests/unit/explorers/document/test_api.py -v`
Expected: all PASS, including the new partial-success tests AND the rewritten unsupported-type test.

#### REFACTOR

- The `_failed_row` helper deduplicates four near-identical `DocumentUploadResponse(project_id="", ..., status="failed", ...)` constructions in the loop. Confirm it's used in all four spots.
- The pairing-by-index for `relative_path` (`relative_path[idx] if ...`) is a candidate for a small `_relpath_for(idx)` helper if it appears more than twice; in this version it's once at the top of the loop, so leave it inline.
- Look at whether the per-file `try` block can be shrunk further. The two early `continue` paths (unsupported extension, oversize) are validations that don't need the bigger try/except — they could move outside it. Leave for now if it doesn't simplify; readability over cleverness.
- Run mypy: `mypy src/ananta/explorers/document/api.py`. Address any new errors.

#### Commit

```bash
git add src/ananta/explorers/document/api.py \
        tests/unit/explorers/document/test_api.py
git commit -m "feat: per-file partial success in upload route"
```

---

### Task A5: Verify `topic_mgr.create()` idempotency

**Requirement:** design "Backend changes" — topic-creation note.

**Files:**
- Inspect: `src/ananta/explorers/shared_ui/topics.py` (or wherever `topic_mgr` lives — `grep -rn "class TopicManager\|def create" src/ananta/explorers/shared_ui/` to find it)
- Test: existing topic-manager test file (search via the same grep)

#### RED

Write a test asserting that calling `create()` twice with the same name does not raise.

```python
def test_create_existing_topic_is_idempotent(state):
    state.topic_mgr.create("Barsoom")
    state.topic_mgr.create("Barsoom")  # should not raise
    assert "Barsoom" in state.topic_mgr.list_topics()
```

Adapt to the actual fixture / API shape in the existing test file.

Run: the relevant pytest path.
Two possible outcomes:
- **PASS unexpectedly:** good — `create()` is already idempotent. Single-file upload to an existing topic has been working because of this. Commit the test as a regression guard.
- **FAIL:** `create()` raises `ValueError` ("topic already exists") on duplicates. The upload route currently catches this and returns 422 — meaning single-file upload to an existing topic is broken in subtle ways (or the route is never called with an existing topic, only via a different code path). Investigate before fixing.

If passes unexpectedly: this confirms the existing behavior; A2/A4 don't need any further change. Commit and move on.

#### GREEN

If the test passes immediately, no implementation change. Skip to Commit.

If the test fails, the fix depends on the topic-manager API:

- If there's a `create_or_get` method, change `upload_documents` to use it instead of `create`.
- If not, swallow the "already exists" error in the upload route:

  ```python
  if topic:
      try:
          state.topic_mgr.create(topic)
      except ValueError as exc:
          if "already exists" not in str(exc).lower():
              raise HTTPException(422, str(exc)) from exc
  ```

Add a separate test that uploads to an existing topic via the route (not just the manager directly) succeeds.

#### REFACTOR

- If the fix swallows errors, consider whether the topic-manager itself should expose a `create_or_get` method for clarity. If yes, do it now in this task; the change is small and isolates the contract.
- If the fix wasn't needed, no refactor.

#### Commit

```bash
git add tests/  # whatever changed
git commit -m "test: verify topic_mgr.create idempotency on existing topic"
```

If a fix was needed, include `src/` in the add and amend the message accordingly.

---

### Task A6: Expose `relative_path` to the RLM via `ParsedDocument.metadata`

**Requirement:** design "Path representation" — RLM-side exposure.

**Files:**
- Modify: `src/ananta/explorers/document/api.py` (the `ParsedDocument(metadata=...)` construction inside `upload_documents`)
- Test: `tests/unit/explorers/document/test_api.py`

#### RED

```python
def test_upload_exposes_relative_path_to_rlm_metadata(
    self,
    client,
    state,  # the explorer state fixture used by other upload tests
    uploads_dir: Path,
):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("README.md", b"hello world", "text/markdown"))],
        data={"relative_path": "docs/api/README.md"},
    )
    assert response.status_code == 200
    [row] = response.json()
    project_id = row["project_id"]

    # The document stored to Ananta storage should expose relative_path in its
    # metadata so the RLM-side document object can read it.
    stored = state.ananta.storage.load_document(project_id)
    assert stored.metadata.get("relative_path") == "docs/api/README.md"
```

If the `state.ananta.storage.load_document` method has a different name, find the right call by inspecting how other tests retrieve stored documents.

Run: `pytest tests/unit/explorers/document/test_api.py -v -k rlm_metadata`
Expected failure: `relative_path` is not in the stored ParsedDocument metadata (it's only in `meta.json`).

#### GREEN

In `api.py`, change the `ParsedDocument` construction inside the per-file loop to include `relative_path`:

```python
doc = ParsedDocument(
    name=file.filename,
    content=text,
    format=ext.lstrip(".") or "txt",
    metadata={
        "filename": file.filename,
        "size": len(content),
        "relative_path": rel_path,
    },
    char_count=len(text),
)
```

Run: `pytest tests/unit/explorers/document/test_api.py -v`
Expected: PASS.

#### REFACTOR

- The `metadata` dict is now built from three keys. If a future requirement adds more (e.g., `upload_session_id` exposed to RLM), this becomes a candidate for a helper. Leave inline for now.
- Confirm that single-file upload (no `relative_path`) stores `relative_path: None` in metadata rather than missing the key — both are fine for downstream code, but consistency with `meta.json` matters.

#### Commit

```bash
git add src/ananta/explorers/document/api.py \
        tests/unit/explorers/document/test_api.py
git commit -m "feat: expose relative_path via ParsedDocument.metadata for RLM"
```

---

### Phase A checkpoint

Run: `make all`
Expected: all green.

---

## Phase B — Frontend folder-walk utility

### Task B1: `folder-walk.ts` — extension allowlist + oversize filter

**Requirement:** design "User-facing flow" step 2 + "Size handling" — pre-flight skipped reasons.

**Files:**
- Create: `src/ananta/explorers/document/frontend/src/lib/folder-walk.ts`
- Create: `src/ananta/explorers/document/frontend/src/components/__tests__/folder-walk.test.ts`

#### RED

```typescript
import { describe, it, expect } from 'vitest'
import { filterFiles, SUPPORTED_EXTENSIONS, MAX_UPLOAD_BYTES } from '../../lib/folder-walk'

describe('filterFiles', () => {
  it('accepts files with supported extensions under the size limit', () => {
    const files = [
      new File([''], 'a.md'),
      new File([''], 'b.pdf'),
      new File([''], 'd.txt'),
    ]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name).sort()).toEqual(['a.md', 'b.pdf', 'd.txt'])
    expect(skipped).toEqual([])
  })

  it('skips files outside the allowlist with reason "unsupported extension"', () => {
    const files = [
      new File([''], 'a.md'),
      new File([''], 'c.png'),
    ]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name)).toEqual(['a.md'])
    expect(skipped).toEqual([
      { file: expect.objectContaining({ name: 'c.png' }), reason: 'unsupported extension' },
    ])
  })

  it('skips oversized files with reason "file exceeds 50 MB limit"', () => {
    const big = new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], 'big.pdf')
    const files = [new File([''], 'small.pdf'), big]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name)).toEqual(['small.pdf'])
    expect(skipped).toEqual([
      { file: expect.objectContaining({ name: 'big.pdf' }), reason: 'file exceeds 50 MB limit' },
    ])
  })

  it('SUPPORTED_EXTENSIONS mirrors the backend allowlist', () => {
    expect(SUPPORTED_EXTENSIONS).toContain('.pdf')
    expect(SUPPORTED_EXTENSIONS).toContain('.md')
    expect(SUPPORTED_EXTENSIONS).toContain('.docx')
    expect(SUPPORTED_EXTENSIONS).not.toContain('.png')
  })
})
```

Run: `cd src/ananta/explorers/document/frontend && npm test -- folder-walk`
Expected failure: module doesn't exist.

#### GREEN

```typescript
// src/ananta/explorers/document/frontend/src/lib/folder-walk.ts

// Mirror of src/ananta/explorers/document/config.py.
// Keep these in sync with the backend; config.py is the source of truth.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024
export const MAX_AGGREGATE_UPLOAD_BYTES = 200 * 1024 * 1024
export const MAX_FOLDER_FILES = 500
export const SOFT_WARN_FOLDER_FILES = 100
export const TARGET_BATCH_BYTES = 50 * 1024 * 1024

// Mirror of src/ananta/explorers/document/extractors.py supported list.
export const SUPPORTED_EXTENSIONS: readonly string[] = [
  '.txt', '.md', '.csv', '.log', '.json', '.yaml', '.yml', '.xml', '.html',
  '.htm', '.ini', '.cfg', '.toml', '.env', '.py', '.js', '.ts', '.java',
  '.c', '.cpp', '.h', '.rs', '.go', '.rb', '.sh', '.bat', '.sql', '.r',
  '.tex', '.pdf', '.docx', '.pptx', '.xlsx', '.rtf',
] as const

export interface SkippedFile {
  file: File
  reason: string
}

export interface FilterResult {
  accepted: File[]
  skipped: SkippedFile[]
}

function getExtension(name: string): string {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i).toLowerCase()
}

export function filterFiles(files: File[]): FilterResult {
  const accepted: File[] = []
  const skipped: SkippedFile[] = []
  for (const file of files) {
    if (!SUPPORTED_EXTENSIONS.includes(getExtension(file.name))) {
      skipped.push({ file, reason: 'unsupported extension' })
    } else if (file.size > MAX_UPLOAD_BYTES) {
      skipped.push({ file, reason: 'file exceeds 50 MB limit' })
    } else {
      accepted.push(file)
    }
  }
  return { accepted, skipped }
}
```

Run: `npm test -- folder-walk`
Expected: PASS.

#### REFACTOR

- Confirm the comment block at the top of the constants section names `config.py` clearly. If a future contributor changes one set without the other, this is the only thing pointing them at the source of truth.
- The `getExtension` helper is private; if other modules need it, export it later. YAGNI for now.
- `'file exceeds 50 MB limit'` is a literal — consider deriving it from `MAX_UPLOAD_BYTES` (`\`file exceeds ${MAX_UPLOAD_BYTES / 1024 / 1024} MB limit\``). Apply if it reads cleanly.

#### Commit

```bash
git add src/ananta/explorers/document/frontend/src/lib/folder-walk.ts \
        src/ananta/explorers/document/frontend/src/components/__tests__/folder-walk.test.ts
git commit -m "feat: folder-walk extension + oversize filter"
```

---

### Task B2: `walkEntries` — recursive `FileSystemEntry` traversal

**Requirement:** design "Data flow" — walk step.

**Files:**
- Modify: `src/ananta/explorers/document/frontend/src/lib/folder-walk.ts`
- Modify: test file from B1

#### RED

```typescript
import { walkEntries, type WalkedFile } from '../../lib/folder-walk'

type FakeEntry =
  | { isFile: true; isDirectory: false; name: string; fullPath: string; file: (cb: (f: File) => void) => void }
  | { isFile: false; isDirectory: true; name: string; fullPath: string; createReader: () => { readEntries: (cb: (e: FakeEntry[]) => void) => void } }

function makeFile(name: string, fullPath: string, content = ''): FakeEntry {
  return {
    isFile: true,
    isDirectory: false,
    name,
    fullPath,
    file: (cb) => cb(new File([content], name)),
  }
}
function makeDir(name: string, fullPath: string, children: FakeEntry[]): FakeEntry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    fullPath,
    createReader: () => {
      let returned = false
      return {
        readEntries: (cb) => {
          cb(returned ? [] : children)
          returned = true
        },
      }
    },
  }
}

describe('walkEntries', () => {
  it('walks a flat directory and produces relative paths', async () => {
    const root = makeDir('papers', '/papers', [
      makeFile('a.md', '/papers/a.md'),
      makeFile('b.pdf', '/papers/b.pdf'),
    ])
    const result: WalkedFile[] = await walkEntries([root as any], 'papers')
    expect(result.map(r => r.relativePath).sort()).toEqual(['a.md', 'b.pdf'])
  })

  it('walks nested directories and produces relative paths', async () => {
    const root = makeDir('papers', '/papers', [
      makeFile('top.md', '/papers/top.md'),
      makeDir('sub', '/papers/sub', [
        makeFile('x.md', '/papers/sub/x.md'),
      ]),
    ])
    const result = await walkEntries([root as any], 'papers')
    expect(result.map(r => r.relativePath).sort()).toEqual(['sub/x.md', 'top.md'])
  })
})
```

Run: `npm test -- folder-walk`
Expected failure: `walkEntries` doesn't exist.

#### GREEN

Append to `folder-walk.ts`:

```typescript
export interface WalkedFile {
  file: File
  relativePath: string
}

interface FileSystemDirectoryReader {
  readEntries: (cb: (entries: FileSystemEntry[]) => void, errCb?: (e: unknown) => void) => void
}
interface FileSystemEntry {
  isFile: boolean
  isDirectory: boolean
  name: string
  fullPath: string
}
interface FileSystemFileEntry extends FileSystemEntry {
  file: (cb: (f: File) => void, errCb?: (e: unknown) => void) => void
}
interface FileSystemDirectoryEntry extends FileSystemEntry {
  createReader: () => FileSystemDirectoryReader
}

function readAllEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = []
    const readBatch = () => {
      reader.readEntries(
        (batch) => {
          if (batch.length === 0) {
            resolve(all)
          } else {
            all.push(...batch)
            readBatch()
          }
        },
        reject,
      )
    }
    readBatch()
  })
}

function getFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

export async function walkEntries(
  entries: FileSystemEntry[],
  rootName: string,
): Promise<WalkedFile[]> {
  const result: WalkedFile[] = []
  const stripPrefix = (fullPath: string): string => {
    const prefix = `/${rootName}/`
    return fullPath.startsWith(prefix)
      ? fullPath.slice(prefix.length)
      : fullPath.replace(/^\//, '')
  }

  const visit = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      const file = await getFile(entry as FileSystemFileEntry)
      result.push({ file, relativePath: stripPrefix(entry.fullPath) })
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      const children = await readAllEntries(reader)
      for (const child of children) {
        await visit(child)
      }
    }
  }

  for (const entry of entries) {
    await visit(entry)
  }
  return result
}
```

Run: `npm test -- folder-walk`
Expected: PASS.

#### REFACTOR

- The `readAllEntries` loop handles a real Safari quirk (incremental batches) — keep the comment-free pattern lean but well-named so future readers understand why.
- `stripPrefix` is local to `walkEntries`; if the click path (B5/C3 below) needs the same logic on `webkitRelativePath` strings, hoist later.

#### Commit

```bash
git add src/ananta/explorers/document/frontend/src/lib/folder-walk.ts \
        src/ananta/explorers/document/frontend/src/components/__tests__/folder-walk.test.ts
git commit -m "feat: recursive walk over FileSystemEntry tree"
```

---

### Task B3: Walk early-bails at `MAX_FOLDER_FILES`

**Requirement:** design "User-facing flow" step 3 — hard 500-file cap.

**Files:**
- Modify: `folder-walk.ts`
- Modify: test file

#### RED

```typescript
import { walkEntries, MAX_FOLDER_FILES } from '../../lib/folder-walk'

describe('walkEntries with cap', () => {
  it('throws when the file count exceeds MAX_FOLDER_FILES', async () => {
    const children = Array.from({ length: MAX_FOLDER_FILES + 100 }, (_, i) =>
      makeFile(`f${i}.md`, `/big/f${i}.md`)
    )
    const root = makeDir('big', '/big', children)
    await expect(walkEntries([root as any], 'big'))
      .rejects.toThrow(/exceed.*folder/i)
  })
})
```

Run: `npm test -- folder-walk`
Expected failure: walk happily collects more than 500 files.

#### GREEN

Modify `walkEntries` to bail when the count exceeds `MAX_FOLDER_FILES`:

```typescript
export async function walkEntries(
  entries: FileSystemEntry[],
  rootName: string,
): Promise<WalkedFile[]> {
  const result: WalkedFile[] = []
  const stripPrefix = ...  // unchanged

  const visit = async (entry: FileSystemEntry): Promise<void> => {
    if (result.length > MAX_FOLDER_FILES) {
      throw new Error(`folder exceeds ${MAX_FOLDER_FILES}-file limit`)
    }
    if (entry.isFile) {
      const file = await getFile(entry as FileSystemFileEntry)
      result.push({ file, relativePath: stripPrefix(entry.fullPath) })
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      const children = await readAllEntries(reader)
      for (const child of children) {
        await visit(child)
      }
    }
  }

  for (const entry of entries) {
    await visit(entry)
  }
  return result
}
```

Run: `npm test -- folder-walk`
Expected: PASS.

#### REFACTOR

- The cap is hard-coded by reading from the imported constant — that's the right level of abstraction. No further parameterization needed.
- The error message is user-facing (the hook will catch it and show in the modal). Confirm the wording is what an end user would understand. "Folder exceeds 500-file limit" is fine.

#### Commit

```bash
git commit -am "feat: walk early-bails at MAX_FOLDER_FILES"
```

---

### Task B4: `partitionIntoBatches` for `TARGET_BATCH_BYTES`

**Requirement:** design "Size handling" — chunked upload partitioning.

**Files:**
- Modify: `folder-walk.ts`
- Modify: test file

#### RED

```typescript
import { partitionIntoBatches, TARGET_BATCH_BYTES } from '../../lib/folder-walk'

describe('partitionIntoBatches', () => {
  it('groups files under the target byte size', () => {
    const files = [
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'a.pdf'), relativePath: 'a.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'b.pdf'), relativePath: 'b.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'c.pdf'), relativePath: 'c.pdf' },
    ]
    const batches = partitionIntoBatches(files, TARGET_BATCH_BYTES)
    expect(batches.length).toBe(2)
    expect(batches[0].length).toBe(2)
    expect(batches[1].length).toBe(1)
  })

  it('places a single file in its own batch when adding the next would exceed target', () => {
    const files = [
      { file: new File([new Uint8Array(40 * 1024 * 1024)], 'big.pdf'), relativePath: 'big.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'small.pdf'), relativePath: 'small.pdf' },
    ]
    const batches = partitionIntoBatches(files, 50 * 1024 * 1024)
    expect(batches.length).toBe(2)
  })

  it('returns an empty array for empty input', () => {
    expect(partitionIntoBatches([], TARGET_BATCH_BYTES)).toEqual([])
  })
})
```

Run: `npm test -- folder-walk`
Expected failure.

#### GREEN

Append:

```typescript
export function partitionIntoBatches(
  files: WalkedFile[],
  targetBytes: number,
): WalkedFile[][] {
  const batches: WalkedFile[][] = []
  let current: WalkedFile[] = []
  let currentBytes = 0
  for (const wf of files) {
    if (current.length > 0 && currentBytes + wf.file.size > targetBytes) {
      batches.push(current)
      current = []
      currentBytes = 0
    }
    current.push(wf)
    currentBytes += wf.file.size
  }
  if (current.length > 0) batches.push(current)
  return batches
}
```

Run: `npm test -- folder-walk`
Expected: PASS.

#### REFACTOR

- The greedy bin-packing is intentionally simple. Don't reach for optimal packing; the ordering of files is fine.
- Look across `folder-walk.ts` for any other place that builds a list-of-lists with similar logic. Currently none — leave as-is.

#### Commit

```bash
git commit -am "feat: partition walked files into target-byte batches"
```

---

### Phase B checkpoint

Run: `cd src/ananta/explorers/document/frontend && npm test`
Then from project root: `make all`
Expected: all green.

---

## Phase C — Frontend UI

### Task C1: Disable `UploadArea` when no topic is selected

**Requirement:** design "User-facing flow" precondition.

**Files:**
- Modify: `src/ananta/explorers/document/frontend/src/components/UploadArea.tsx`
- Modify: `src/ananta/explorers/document/frontend/src/components/__tests__/UploadArea.test.tsx`

#### RED

```tsx
it('disables drop zone when activeTopic is null', () => {
  render(<UploadArea onUpload={vi.fn()} activeTopic={null} />)
  const zone = screen.getByRole('button', { name: /upload/i })
  expect(zone).toHaveAttribute('aria-disabled', 'true')
  expect(zone.textContent?.toLowerCase()).toContain('select a topic')
})

it('enables drop zone when activeTopic is provided', () => {
  render(<UploadArea onUpload={vi.fn()} activeTopic="Barsoom" />)
  const zone = screen.getByRole('button', { name: /upload/i })
  expect(zone).not.toHaveAttribute('aria-disabled', 'true')
})
```

Run: `npm test -- UploadArea`
Expected failure: `activeTopic` prop unrecognized.

#### GREEN

Update `UploadArea.tsx`:

```tsx
interface UploadAreaProps {
  onUpload: (files: File[]) => Promise<void>
  activeTopic: string | null
}

export default function UploadArea({ onUpload, activeTopic }: UploadAreaProps) {
  const disabled = activeTopic === null
  // ...existing state hooks...
  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload files"
      aria-disabled={disabled || undefined}
      onDragOver={disabled ? undefined : (e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={disabled ? undefined : () => setDragging(false)}
      onDrop={disabled ? undefined : handleDrop}
      onClick={disabled ? undefined : () => inputRef.current?.click()}
      className={`... ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      ...
      {disabled
        ? 'Select a topic first'
        : (uploading ? 'Uploading...' : 'Drop files here or click to upload')}
    </div>
  )
}
```

Update `App.tsx` to pass `activeTopic={activeTopic}`. Find with `grep -n "<UploadArea" src/ananta/explorers/document/frontend/src/App.tsx`.

Run: `npm test`
Expected: PASS.

#### REFACTOR

- The repeated `disabled ? undefined : ...` pattern hurts readability. Consider hoisting the handlers:

  ```tsx
  const handlers = disabled ? {} : {
    onDragOver: (e) => { e.preventDefault(); setDragging(true) },
    onDrop: handleDrop,
    onClick: () => inputRef.current?.click(),
    onDragLeave: () => setDragging(false),
  }
  return <div {...handlers} ... />
  ```

  Apply if it reads cleaner.
- Make sure the hover/focus styling still works when enabled (existing tests should cover this; if not, add a quick visual check in the manual verification at D5).

#### Commit

```bash
git commit -am "feat: disable upload zone when no topic is selected"
```

---

### Task C2: Detect directory drops, route to `onFolderUpload`

**Requirement:** design "User-facing flow" step 1 — drag path.

**Files:**
- Modify: `UploadArea.tsx`
- Modify: `UploadArea.test.tsx`

#### RED

```tsx
it('routes directory drops to onFolderUpload', async () => {
  const onFolderUpload = vi.fn(async () => {})
  const onUpload = vi.fn()
  render(<UploadArea onUpload={onUpload} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

  const fakeDirEntry = { isDirectory: true, isFile: false, name: 'papers', fullPath: '/papers' }
  const dataTransfer = {
    files: [],
    items: [{ webkitGetAsEntry: () => fakeDirEntry }],
  } as unknown as DataTransfer

  const zone = screen.getByRole('button', { name: /upload/i })
  fireEvent.drop(zone, { dataTransfer })

  await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
  expect(onUpload).not.toHaveBeenCalled()
})

it('routes plain file drops to onUpload', async () => {
  const onFolderUpload = vi.fn(async () => {})
  const onUpload = vi.fn(async () => {})
  render(<UploadArea onUpload={onUpload} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

  const file = new File(['x'], 'a.md')
  const fakeFileEntry = { isFile: true, isDirectory: false, name: 'a.md', fullPath: '/a.md' }
  const dataTransfer = {
    files: [file],
    items: [{ webkitGetAsEntry: () => fakeFileEntry }],
  } as unknown as DataTransfer

  const zone = screen.getByRole('button', { name: /upload/i })
  fireEvent.drop(zone, { dataTransfer })

  await waitFor(() => expect(onUpload).toHaveBeenCalled())
  expect(onFolderUpload).not.toHaveBeenCalled()
})
```

Run: `npm test -- UploadArea`
Expected failure.

#### GREEN

```tsx
interface UploadAreaProps {
  onUpload: (files: File[]) => Promise<void>
  onFolderUpload?: (entries: FileSystemEntry[], rootName: string) => Promise<void>
  activeTopic: string | null
}

const handleDrop = useCallback(async (e: DragEvent<HTMLDivElement>) => {
  e.preventDefault()
  setDragging(false)
  if (disabled) return

  const items = Array.from(e.dataTransfer.items ?? [])
  const entries: FileSystemEntry[] = []
  let rootName = ''
  for (const item of items) {
    const entry = (item as DataTransferItem & { webkitGetAsEntry: () => FileSystemEntry | null }).webkitGetAsEntry()
    if (entry) {
      entries.push(entry)
      if (entry.isDirectory && !rootName) rootName = entry.name
    }
  }

  const hasDirectory = entries.some(e => e.isDirectory)
  if (hasDirectory && onFolderUpload) {
    await onFolderUpload(entries, rootName)
  } else {
    await handleFiles(e.dataTransfer.files)
  }
}, [disabled, handleFiles, onFolderUpload])
```

Run: `npm test -- UploadArea`
Expected: PASS.

#### REFACTOR

- The `webkitGetAsEntry` cast is gnarly. If a similar cast appears in C3 (folder-button click handler — actually no, the click path uses `webkitRelativePath`, not `webkitGetAsEntry`), it'd be worth a tiny helper. For now leave inline.
- Check that the drop handler is still bound to the keyboard "Enter/Space" path correctly (those open the file picker, not folder picker — that's by design).

#### Commit

```bash
git commit -am "feat: route directory drops to folder-upload handler"
```

---

### Task C3: "Upload folder" click button via `webkitdirectory`

**Requirement:** design "Frontend changes" — click-path folder upload.

**Files:**
- Modify: `UploadArea.tsx` (add a second input + button)
- Modify: `UploadArea.test.tsx`

#### RED

```tsx
it('renders an "Upload folder" button when enabled', () => {
  render(<UploadArea onUpload={vi.fn()} onFolderUpload={vi.fn()} activeTopic="Barsoom" />)
  expect(screen.getByRole('button', { name: /upload folder/i })).toBeInTheDocument()
})

it('does not render "Upload folder" when no topic selected', () => {
  render(<UploadArea onUpload={vi.fn()} onFolderUpload={vi.fn()} activeTopic={null} />)
  expect(screen.queryByRole('button', { name: /upload folder/i })).toBeNull()
})

it('routes click-selected folder files to onFolderUpload as WalkedFile[]', async () => {
  const onFolderUpload = vi.fn(async () => {})
  render(<UploadArea onUpload={vi.fn()} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

  const file1 = new File(['x'], 'a.md')
  Object.defineProperty(file1, 'webkitRelativePath', { value: 'papers/a.md' })
  const file2 = new File(['y'], 'b.md')
  Object.defineProperty(file2, 'webkitRelativePath', { value: 'papers/sub/b.md' })

  const folderInput = screen.getByLabelText(/folder picker/i) as HTMLInputElement
  Object.defineProperty(folderInput, 'files', { value: [file1, file2], writable: false })
  fireEvent.change(folderInput)

  await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
  // Should be called with WalkedFile[] (the click path skips webkitGetAsEntry).
  const [walked, rootName] = onFolderUpload.mock.calls[0]
  expect(rootName).toBe('papers')
  expect(walked.map((w: any) => w.relativePath).sort()).toEqual(['a.md', 'sub/b.md'])
})
```

NOTE: The existing `onFolderUpload` signature accepts `(entries, rootName)`. The click path produces `WalkedFile[]` directly (no `FileSystemEntry`). Either:
- Widen the callback type to accept either `FileSystemEntry[]` OR `WalkedFile[]`, with a discriminator,
- Or have `UploadArea` always emit a uniform shape — we'll choose the second.

Update the props typing accordingly:

```tsx
onFolderUpload?: (input:
  | { kind: 'entries'; entries: FileSystemEntry[]; rootName: string }
  | { kind: 'walked'; files: WalkedFile[]; rootName: string }
) => Promise<void>
```

The drop test from C2 also needs to be updated to wrap the entries in `{ kind: 'entries', ... }`. Update both C2's tests and the impl in this task accordingly. (This is a minor breaking change to C2's contract that surfaces only because we now have two callers.)

Run: `npm test -- UploadArea`
Expected failure.

#### GREEN

In `UploadArea.tsx`:

```tsx
const folderInputRef = useRef<HTMLInputElement>(null)

const handleFolderInputChange = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
  const files = Array.from(e.target.files ?? [])
  if (files.length === 0 || !onFolderUpload) return
  // Convert FileList into WalkedFile[] using webkitRelativePath.
  // The first segment of webkitRelativePath is the root folder name.
  const firstPath = (files[0] as File & { webkitRelativePath: string }).webkitRelativePath
  const rootName = firstPath.split('/')[0] ?? ''
  const walked: WalkedFile[] = files.map((f) => {
    const wp = (f as File & { webkitRelativePath: string }).webkitRelativePath
    const relativePath = wp.startsWith(`${rootName}/`) ? wp.slice(rootName.length + 1) : wp
    return { file: f, relativePath }
  })
  await onFolderUpload({ kind: 'walked', files: walked, rootName })
}, [onFolderUpload])

// In the JSX, alongside the existing drop zone:
{!disabled && (
  <button
    type="button"
    onClick={() => folderInputRef.current?.click()}
    aria-label="Upload folder"
  >
    Upload folder
  </button>
)}
<input
  ref={folderInputRef}
  type="file"
  // @ts-expect-error - webkitdirectory is not in standard TS DOM types
  webkitdirectory=""
  className="hidden"
  aria-label="folder picker"
  onChange={handleFolderInputChange}
/>
```

Update C2's drop handler to wrap its emission:

```tsx
if (hasDirectory && onFolderUpload) {
  await onFolderUpload({ kind: 'entries', entries, rootName })
}
```

Run: `npm test -- UploadArea`
Expected: PASS (including the updated C2 tests).

#### REFACTOR

- The `webkitRelativePath` field isn't in standard DOM types. Define a small local `FileWithPath` interface and cast through that for cleanliness.
- The discriminated-union shape (`kind: 'entries' | 'walked'`) is the seam where the hook in D2 unifies both paths. Make sure the shape is named/documented well.
- Confirm the folder button visually fits next to the existing drop zone — this is a styling matter; if it looks ugly, move it to a separate row.

#### Commit

```bash
git commit -am "feat: 'Upload folder' click button via webkitdirectory"
```

---

### Task C4: `FolderUploadModal` — pre-flight state

**Requirement:** design "User-facing flow" step 4 — pre-flight modal.

**Files:**
- Create: `src/ananta/explorers/document/frontend/src/components/FolderUploadModal.tsx`
- Create: `src/ananta/explorers/document/frontend/src/components/__tests__/FolderUploadModal.test.tsx`

#### RED

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import FolderUploadModal from '../FolderUploadModal'
import { SOFT_WARN_FOLDER_FILES } from '../../lib/folder-walk'

describe('FolderUploadModal pre-flight', () => {
  const baseFiles = [
    { file: new File(['x'], 'a.md'), relativePath: 'a.md' },
    { file: new File(['y'], 'b.md'), relativePath: 'sub/b.md' },
  ]

  it('renders target topic, file count, and total bytes', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/Barsoom/)).toBeInTheDocument()
    expect(screen.getByText(/2 files/i)).toBeInTheDocument()
  })

  it('shows soft warning above SOFT_WARN_FOLDER_FILES', () => {
    const many = Array.from({ length: SOFT_WARN_FOLDER_FILES + 50 }, (_, i) => ({
      file: new File(['x'], `f${i}.md`),
      relativePath: `f${i}.md`,
    }))
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: many, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('does not show soft warning at or below SOFT_WARN_FOLDER_FILES', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('groups skipped files by reason', () => {
    render(
      <FolderUploadModal
        state={{
          kind: 'preflight',
          accepted: baseFiles,
          skipped: [
            { file: new File([''], 'x.png'), reason: 'unsupported extension' },
            { file: new File([''], 'y.png'), reason: 'unsupported extension' },
            { file: new File([''], 'big.pdf'), reason: 'file exceeds 50 MB limit' },
          ],
          targetTopic: 'Barsoom',
        }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/2.*unsupported extension/i)).toBeInTheDocument()
    expect(screen.getByText(/1.*exceeds 50 MB/i)).toBeInTheDocument()
  })

  it('calls onContinue when Continue clicked', () => {
    const onContinue = vi.fn()
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={onContinue}
        onCancel={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(onContinue).toHaveBeenCalled()
  })
})
```

Run: `npm test -- FolderUploadModal`
Expected failure.

#### GREEN

Create `FolderUploadModal.tsx`:

```tsx
import { useMemo } from 'react'
import type { WalkedFile, SkippedFile } from '../lib/folder-walk'
import { SOFT_WARN_FOLDER_FILES } from '../lib/folder-walk'

export type ModalState =
  | { kind: 'preflight'; accepted: WalkedFile[]; skipped: SkippedFile[]; targetTopic: string }
  | { kind: 'progress'; total: number; completed: number; currentBatch: number; totalBatches: number }
  | { kind: 'summary'; ingested: number; failed: { name: string; reason: string }[]; skipped: { name: string; reason: string }[] }

interface Props {
  state: ModalState
  onContinue: () => void
  onCancel: () => void
}

export default function FolderUploadModal({ state, onContinue, onCancel }: Props) {
  if (state.kind === 'preflight') {
    return <PreflightView state={state} onContinue={onContinue} onCancel={onCancel} />
  }
  return null  // progress/summary added in C5
}

function PreflightView({
  state,
  onContinue,
  onCancel,
}: {
  state: Extract<ModalState, { kind: 'preflight' }>
  onContinue: () => void
  onCancel: () => void
}) {
  const totalBytes = useMemo(
    () => state.accepted.reduce((sum, f) => sum + f.file.size, 0),
    [state.accepted],
  )
  const skippedByReason = useMemo(() => {
    const m = new Map<string, number>()
    for (const s of state.skipped) m.set(s.reason, (m.get(s.reason) ?? 0) + 1)
    return [...m.entries()]
  }, [state.skipped])
  const showWarning = state.accepted.length > SOFT_WARN_FOLDER_FILES

  return (
    <div role="dialog" aria-label="Folder upload preview">
      <h2>Upload to: {state.targetTopic}</h2>
      <p>{state.accepted.length} files ({formatBytes(totalBytes)})</p>
      {showWarning && (
        <p role="alert">
          This will add {state.accepted.length} files. Continue?
        </p>
      )}
      {skippedByReason.length > 0 && (
        <div>
          <h3>Skipped</h3>
          <ul>
            {skippedByReason.map(([reason, count]) => (
              <li key={reason}>{count} {reason}</li>
            ))}
          </ul>
        </div>
      )}
      <button onClick={onContinue}>Continue</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  )
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
```

Run: `npm test -- FolderUploadModal`
Expected: PASS.

#### REFACTOR

- `formatBytes` is local; if a similar helper exists elsewhere in the frontend (`grep -rn "formatBytes\|formatSize" src/ananta/explorers/document/frontend/src/`), unify. If not, leave local.
- The `skippedByReason` Map → array conversion is fine but consider whether the ordering is stable across runs. `Map` preserves insertion order, so the displayed list matches the order skips were encountered — acceptable.

#### Commit

```bash
git add src/ananta/explorers/document/frontend/src/components/FolderUploadModal.tsx \
        src/ananta/explorers/document/frontend/src/components/__tests__/FolderUploadModal.test.tsx
git commit -m "feat: FolderUploadModal pre-flight view"
```

---

### Task C5: `FolderUploadModal` — progress + summary states

**Requirement:** design "User-facing flow" steps 5 + 6.

**Files:**
- Modify: `FolderUploadModal.tsx`
- Modify: `FolderUploadModal.test.tsx`

#### RED

```tsx
describe('FolderUploadModal progress', () => {
  it('renders a progress indicator', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'progress', total: 100, completed: 30, currentBatch: 2, totalBatches: 5 }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/30 of 100/)).toBeInTheDocument()
    expect(screen.getByText(/batch 2 of 5/i)).toBeInTheDocument()
  })

  it('cancel button is enabled', () => {
    const onCancel = vi.fn()
    render(
      <FolderUploadModal
        state={{ kind: 'progress', total: 100, completed: 30, currentBatch: 2, totalBatches: 5 }}
        onContinue={() => {}}
        onCancel={onCancel}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})

describe('FolderUploadModal summary', () => {
  it('renders ingested / failed / skipped rows', () => {
    render(
      <FolderUploadModal
        state={{
          kind: 'summary',
          ingested: 47,
          failed: [{ name: 'bad.pdf', reason: 'text extraction failed' }],
          skipped: [{ name: 'logo.png', reason: 'unsupported extension' }],
        }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/47/)).toBeInTheDocument()
    expect(screen.getByText('bad.pdf')).toBeInTheDocument()
    expect(screen.getByText('logo.png')).toBeInTheDocument()
  })
})
```

Run: `npm test -- FolderUploadModal`
Expected failure.

#### GREEN

Replace the `return null` branches with `ProgressView` and `SummaryView` components.

```tsx
function ProgressView({
  state, onCancel,
}: {
  state: Extract<ModalState, { kind: 'progress' }>
  onCancel: () => void
}) {
  const pct = state.total > 0 ? Math.round((state.completed / state.total) * 100) : 0
  return (
    <div role="dialog" aria-label="Folder upload progress">
      <p>Uploading {state.completed} of {state.total} files… (batch {state.currentBatch} of {state.totalBatches})</p>
      <progress value={pct} max={100} />
      <button onClick={onCancel}>Cancel</button>
    </div>
  )
}

function SummaryView({
  state, onContinue,
}: {
  state: Extract<ModalState, { kind: 'summary' }>
  onContinue: () => void  // re-purpose as "Close" button handler
}) {
  return (
    <div role="dialog" aria-label="Folder upload summary">
      <p>{state.ingested} ingested</p>
      {state.failed.length > 0 && (
        <div>
          <h3>Failed ({state.failed.length})</h3>
          <ul>{state.failed.map((f, i) => <li key={i}>{f.name} — {f.reason}</li>)}</ul>
        </div>
      )}
      {state.skipped.length > 0 && (
        <div>
          <h3>Skipped ({state.skipped.length})</h3>
          <ul>{state.skipped.map((s, i) => <li key={i}>{s.name} — {s.reason}</li>)}</ul>
        </div>
      )}
      <button onClick={onContinue}>Close</button>
    </div>
  )
}

// Update top-level dispatch:
if (state.kind === 'preflight') return <PreflightView ... />
if (state.kind === 'progress') return <ProgressView state={state} onCancel={onCancel} />
if (state.kind === 'summary') return <SummaryView state={state} onContinue={onContinue} />
return null
```

Run: `npm test -- FolderUploadModal`
Expected: PASS.

#### REFACTOR

- `onContinue` is now overloaded as "Close" in summary view. If this confuses readers, rename the prop to `onPrimary` or split into `onContinue` + `onClose`. Apply if it reads cleaner.
- Look for shared dialog framing across all three states (`<div role="dialog">`); extract a small `<ModalShell>` wrapper if duplication is annoying.

#### Commit

```bash
git commit -am "feat: FolderUploadModal progress and summary views"
```

---

### Phase C checkpoint

Run: `npm test`
Expected: all green.

---

## Phase D — Wire-up + integration

### Task D1: API client — chunked upload with cancel

**Requirement:** design "Failure handling" + "Cancel" — multi-batch orchestration.

**Files:**
- Modify: `src/ananta/explorers/document/frontend/src/api/documents.ts` (find via `grep -rn "documents/upload" src/ananta/explorers/document/frontend/src`)
- Test: alongside (vitest with global `fetch` mock).

#### RED

```typescript
import { uploadFolderInBatches, type UploadRow } from '../api/documents'

describe('uploadFolderInBatches', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [
        { project_id: 'p1', filename: 'a.md', status: 'created' },
      ],
    } as Response))
  })

  it('sends each batch sequentially and aggregates responses', async () => {
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    const result = await uploadFolderInBatches(batches, 'Barsoom', 'session-uuid', () => {})
    expect((global.fetch as any).mock.calls.length).toBe(2)
    expect(result.length).toBe(2)
  })

  it('halts after current batch when cancel signal fires', async () => {
    const ctrl = new AbortController()
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
      [{ file: new File(['z'], 'c.md'), relativePath: 'c.md' }],
    ]
    const promise = uploadFolderInBatches(batches, 'Barsoom', 'sid', () => {}, ctrl.signal)
    queueMicrotask(() => ctrl.abort())
    await promise
    expect((global.fetch as any).mock.calls.length).toBeLessThan(3)
  })

  it('reports progress to the callback', async () => {
    const onProgress = vi.fn()
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    await uploadFolderInBatches(batches, 'Barsoom', 'sid', onProgress)
    expect(onProgress).toHaveBeenCalledWith(1, 2, 1, 2)
    expect(onProgress).toHaveBeenCalledWith(2, 2, 2, 2)
  })
})
```

Run: `npm test -- documents`
Expected failure.

#### GREEN

Add to `documents.ts`:

```typescript
import type { WalkedFile } from '../lib/folder-walk'

export interface UploadRow {
  project_id: string
  filename: string
  status: 'created' | 'failed'
  reason?: string
}

export async function uploadFolderInBatches(
  batches: WalkedFile[][],
  topic: string,
  sessionId: string,
  onProgress: (completed: number, total: number, currentBatch: number, totalBatches: number) => void,
  signal?: AbortSignal,
): Promise<UploadRow[]> {
  const total = batches.reduce((s, b) => s + b.length, 0)
  let completed = 0
  const all: UploadRow[] = []

  for (let i = 0; i < batches.length; i++) {
    if (signal?.aborted) break
    const batch = batches[i]
    const form = new FormData()
    for (const wf of batch) {
      form.append('files', wf.file, wf.file.name)
      form.append('relative_path', wf.relativePath)
    }
    form.append('topic', topic)
    form.append('upload_session_id', sessionId)

    const res = await fetch('/api/documents/upload', { method: 'POST', body: form })
    if (!res.ok) {
      throw new Error(`upload failed: ${res.status}`)
    }
    const rows = (await res.json()) as UploadRow[]
    all.push(...rows)
    completed += batch.length
    onProgress(completed, total, i + 1, batches.length)
  }

  return all
}
```

Run: `npm test -- documents`
Expected: PASS.

#### REFACTOR

- The deliberate non-passing of `signal` to `fetch` is a design decision (cancel-between-batches, not mid-batch). Add a one-line comment in the source noting this so a future contributor doesn't "fix" it.
- Look for any other helper in `documents.ts` that constructs a `FormData` from files; if there's a duplicated pattern, extract.

#### Commit

```bash
git commit -am "feat: chunked folder-upload api client with cancel-between-batches"
```

---

### Task D2: `useFolderUpload` hook + `App.tsx` wiring

**Requirement:** design "User-facing flow" — orchestration end-to-end.

**Files:**
- Create: `src/ananta/explorers/document/frontend/src/lib/use-folder-upload.ts`
- Create: `src/ananta/explorers/document/frontend/src/components/__tests__/use-folder-upload.test.ts`
- Modify: `src/ananta/explorers/document/frontend/src/App.tsx`

#### RED

```typescript
import { renderHook, act } from '@testing-library/react'
import { useFolderUpload } from '../lib/use-folder-upload'

it('starts with no state', () => {
  const { result } = renderHook(() => useFolderUpload())
  expect(result.current.state).toBeNull()
})

it('walking entries transitions to preflight', async () => {
  const fakeFile = {
    isFile: true, isDirectory: false, name: 'a.md', fullPath: '/x/a.md',
    file: (cb: any) => cb(new File(['x'], 'a.md')),
  }
  const fakeRoot = {
    isFile: false, isDirectory: true, name: 'x', fullPath: '/x',
    createReader: () => { let r = false; return { readEntries: (cb: any) => { cb(r ? [] : [fakeFile]); r = true } } },
  }
  const { result } = renderHook(() => useFolderUpload())
  await act(async () => {
    await result.current.start({ kind: 'entries', entries: [fakeRoot as any], rootName: 'x' }, 'Barsoom')
  })
  expect(result.current.state?.kind).toBe('preflight')
})

it('walked-file path transitions to preflight without re-walking', async () => {
  const files = [
    { file: new File(['x'], 'a.md'), relativePath: 'a.md' },
    { file: new File(['y'], 'b.md'), relativePath: 'sub/b.md' },
  ]
  const { result } = renderHook(() => useFolderUpload())
  await act(async () => {
    await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
  })
  expect(result.current.state?.kind).toBe('preflight')
})
```

Run: `npm test -- use-folder-upload`
Expected failure.

#### GREEN

Create the hook:

```typescript
// src/lib/use-folder-upload.ts
import { useCallback, useState } from 'react'
import { walkEntries, filterFiles, partitionIntoBatches, TARGET_BATCH_BYTES, type WalkedFile, type SkippedFile } from './folder-walk'
import { uploadFolderInBatches, type UploadRow } from '../api/documents'
import type { ModalState } from '../components/FolderUploadModal'

type FolderInput =
  | { kind: 'entries'; entries: FileSystemEntry[]; rootName: string }
  | { kind: 'walked'; files: WalkedFile[]; rootName: string }

export function useFolderUpload() {
  const [state, setState] = useState<ModalState | null>(null)
  const [pending, setPending] = useState<{ accepted: WalkedFile[]; topic: string } | null>(null)
  const [abortCtl, setAbortCtl] = useState<AbortController | null>(null)

  const start = useCallback(async (input: FolderInput, topic: string) => {
    let walked: WalkedFile[]
    if (input.kind === 'entries') {
      try {
        walked = await walkEntries(input.entries, input.rootName)
      } catch (err) {
        // Hard cap exceeded — surface as a summary with a single "skipped" row.
        setState({
          kind: 'summary',
          ingested: 0,
          failed: [],
          skipped: [{ name: input.rootName, reason: (err as Error).message }],
        })
        return
      }
    } else {
      walked = input.files
    }
    const { accepted, skipped } = filterFiles(walked.map(w => w.file))
    // filterFiles takes File[]; rebuild WalkedFile[] for accepted.
    const acceptedWalked: WalkedFile[] = walked.filter(w => accepted.includes(w.file))
    const skippedTyped: SkippedFile[] = skipped
    setState({ kind: 'preflight', accepted: acceptedWalked, skipped: skippedTyped, targetTopic: topic })
    setPending({ accepted: acceptedWalked, topic })
  }, [])

  const confirm = useCallback(async () => {
    if (!pending) return
    const { accepted, topic } = pending
    const batches = partitionIntoBatches(accepted, TARGET_BATCH_BYTES)
    const total = accepted.length
    const sessionId = crypto.randomUUID()
    const ctl = new AbortController()
    setAbortCtl(ctl)
    setState({ kind: 'progress', total, completed: 0, currentBatch: 0, totalBatches: batches.length })
    let rows: UploadRow[] = []
    try {
      rows = await uploadFolderInBatches(batches, topic, sessionId,
        (completed, totalCnt, currentBatch, totalBatches) => {
          setState({ kind: 'progress', total: totalCnt, completed, currentBatch, totalBatches })
        },
        ctl.signal,
      )
    } finally {
      setAbortCtl(null)
    }
    const ingested = rows.filter(r => r.status === 'created').length
    const failed = rows.filter(r => r.status === 'failed').map(r => ({ name: r.filename, reason: r.reason ?? 'failed' }))
    // Skipped rows from preflight phase don't show up in `rows`; carry them
    // through from the previous state if needed.
    setState({ kind: 'summary', ingested, failed, skipped: [] })
    setPending(null)
  }, [pending])

  const cancel = useCallback(() => {
    abortCtl?.abort()
    setState(null)
    setPending(null)
  }, [abortCtl])

  return { state, start, confirm, cancel }
}
```

Wire into `App.tsx`:

```tsx
import { useFolderUpload } from './lib/use-folder-upload'
import FolderUploadModal from './components/FolderUploadModal'

const folderUpload = useFolderUpload()

<UploadArea
  onUpload={handleUpload}
  onFolderUpload={(input) => folderUpload.start(input, activeTopic ?? '')}
  activeTopic={activeTopic}
/>

{folderUpload.state && (
  <FolderUploadModal
    state={folderUpload.state}
    onContinue={folderUpload.state.kind === 'preflight' ? folderUpload.confirm : folderUpload.cancel}
    onCancel={folderUpload.cancel}
  />
)}
```

Run: `npm test`
Expected: all PASS.

#### REFACTOR

- The "filter accepted, but rebuild WalkedFile[] from the subset" pattern (`walked.filter(w => accepted.includes(w.file))`) is O(n²) but for n ≤ 500 it's fine. Don't pre-optimize.
- The `confirm` flow drops the pre-flight skipped rows in the summary. That's a real bug — surface them. Carry them through:
  ```typescript
  const preflightSkipped = state?.kind === 'preflight' ? state.skipped : []
  // ...
  setState({ kind: 'summary', ingested, failed, skipped: preflightSkipped.map(s => ({ name: s.file.name, reason: s.reason })) })
  ```
  Update the test to assert the carry-through.
- The `setState` calls during progress are tightly typed via `ModalState`; mypy/typescript should catch any drift.

#### Commit

```bash
git add src/ananta/explorers/document/frontend/src/lib/use-folder-upload.ts \
        src/ananta/explorers/document/frontend/src/components/__tests__/use-folder-upload.test.ts \
        src/ananta/explorers/document/frontend/src/App.tsx
git commit -m "feat: useFolderUpload hook orchestrates walk → preflight → upload → summary"
```

---

### Task D3: Display `relative_path` in document list

**Requirement:** design "Path representation" — UI subtitle.

**Files:**
- Modify: `src/ananta/explorers/document/frontend/src/components/DocumentItem.tsx`
- Modify: `src/ananta/explorers/document/frontend/src/types.ts` (if needed)
- Modify or create: `src/ananta/explorers/document/frontend/src/components/__tests__/DocumentItem.test.tsx`

#### RED

```tsx
it('renders relative_path as a subtitle when present', () => {
  render(<DocumentItem doc={{
    project_id: 'p1',
    filename: 'README.md',
    content_type: 'text/markdown',
    size: 100,
    upload_date: '2026-05-05T00:00:00Z',
    page_count: null,
    relative_path: 'docs/api/README.md',
    upload_session_id: null,
  } as any} />)
  expect(screen.getByText('docs/api/README.md')).toBeInTheDocument()
})

it('does not render a path subtitle when relative_path is null', () => {
  const { container } = render(<DocumentItem doc={{
    project_id: 'p1',
    filename: 'README.md',
    content_type: 'text/markdown',
    size: 100,
    upload_date: '2026-05-05T00:00:00Z',
    page_count: null,
    relative_path: null,
    upload_session_id: null,
  } as any} />)
  // Look for the specific subtitle slot we'll add. If no slot, this assertion
  // becomes "no element with class 'relative-path-subtitle'" or similar.
  expect(container.querySelector('[data-testid="relative-path"]')).toBeNull()
})
```

Run: `npm test -- DocumentItem`
Expected failure.

#### GREEN

Update `DocumentItem.tsx` to render the path under the filename:

```tsx
{doc.relative_path && (
  <div data-testid="relative-path" className="text-xs text-text-dim">
    {doc.relative_path}
  </div>
)}
```

Update `types.ts` `DocumentInfo` to include `relative_path?: string | null` and `upload_session_id?: string | null` (matching the backend schema).

Run: `npm test -- DocumentItem`
Expected: PASS.

#### REFACTOR

- If `DocumentItem` already has multiple subtitle slots, factor them into a uniform pattern.
- Confirm the styling matches existing subtitles (font size, color, spacing).

#### Commit

```bash
git commit -am "feat: show relative_path as subtitle in document list"
```

---

### Task D4: CHANGELOG entry + manual verification

**Requirement:** design "Risks and open issues" (CHANGELOG note) + manual smoke.

**Files:**
- Modify: `CHANGELOG.md`

#### RED

(No automated test for documentation. Skip RED.)

#### GREEN

Under `[Unreleased]`:

```markdown
### Added
- Document Explorer: folder upload. Drop a folder onto the explorer (or use the
  new "Upload folder" button) to recursively upload its supported files into
  the currently selected topic. Pre-flight modal previews counts, byte totals,
  and skipped reasons; progress modal shows per-batch upload; summary modal
  reports ingested / failed / skipped per file. Drop is disabled when no
  topic is selected. (See docs/plans/2026-05-05-folder-upload-design.md.)
- Document Explorer: documents now expose a `relative_path` field (in API
  responses, UI subtitle, and `ParsedDocument.metadata`) so the LLM can
  filter or group by folder structure.

### Changed
- Document Explorer: multi-file upload now returns per-file partial-success
  rows instead of failing the whole request on one bad file. Each
  `DocumentUploadResponse` row carries `status` (`"created"` or `"failed"`)
  and an optional `reason`. Single-file uploads are observably unchanged.
- Document Explorer: upload limits centralized in
  `src/ananta/explorers/document/config.py`. No behavior change.
```

Manual verification:

```bash
./document-explorer/document-explorer.sh
```

Test cases:
1. With no topic selected, drop a folder. Expected: drop zone shows "Select a topic first" and no upload starts.
2. Select a topic, drop a small folder of mixed PDF/MD/PNG. Expected: pre-flight modal shows correct counts and skipped PNG ("unsupported extension"). Continue. Summary shows PDFs/MDs ingested.
3. Select a topic, drop a folder with a >50 MB file. Expected: pre-flight modal shows it skipped with reason "file exceeds 50 MB limit"; bytes never sent.
4. Drop a folder with > 500 files (e.g., a `node_modules`-heavy project). Expected: error surface explains "exceeds 500-file limit"; no upload starts.
5. Drop a folder containing one corrupt PDF. Expected: summary reports that one as failed, the others as ingested.
6. Click "Upload folder" button (no drag), pick a folder. Expected: same flow as drop.

If any test fails, file findings as new tasks.

#### REFACTOR

- Re-read the CHANGELOG entries for tone and accuracy. The "Changed" entry for the upload contract is the most important; it's a behavior change.

#### Commit

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entries for folder upload feature"
```

---

## Final checkpoint

```bash
make all
cd src/ananta/explorers/document/frontend && npm test
```

Expected: all green.

When ready to merge, use the `/release` skill — see CLAUDE.md.

---

## Out of scope (tracked in TODO.md)

- Sensitive-info filtering (dotfiles, dot-dirs, cruft directories, `.env`/`.py` exclusion).
- All-or-nothing rollback across batches (a future `DELETE /api/documents/upload-session/{id}` endpoint, using the `upload_session_id` we're already recording).
- Auto-create topic from folder name.
- Runtime configurability of upload limits via env vars or settings file.

These are intentional v1 cuts. Don't sneak them in during implementation.
