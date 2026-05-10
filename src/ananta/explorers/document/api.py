"""Document explorer API.

Provides document upload, CRUD, and topic-document reference routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ananta.explorers.document.config import (
    MAX_AGGREGATE_UPLOAD_BYTES,
    MAX_FOLDER_FILES,
    MAX_UPLOAD_BYTES,
)
from ananta.explorers.document.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from ananta.explorers.document.extractors import (
    extract_text,
    get_page_count,
    is_supported_extension,
)
from ananta.explorers.document.schemas import (
    DocumentInfo,
    DocumentRename,
    DocumentUploadResponse,
)
from ananta.explorers.document.topics import _slugify
from ananta.explorers.document.websockets import websocket_handler
from ananta.explorers.shared_ui.app_factory import create_app
from ananta.explorers.shared_ui.routes import create_item_router, create_shared_router
from ananta.models import ParsedDocument

_logger = logging.getLogger(__name__)

# relative_path is untrusted user input that ends up persisted to meta.json,
# ParsedDocument.metadata, and rendered in the UI.
#
# We use a denylist rather than a tight allowlist (I1): the previous regex
# blocked common legitimate filename punctuation — apostrophes, parens,
# brackets, commas, ampersands, plus signs, etc. — so a folder of real-world
# files (a project repo with READMEs, a personal docs tree) silently
# produced "invalid relative_path" failed rows for files that were
# otherwise fine.
#
# What we reject (not what we allow):
#   * empty / None — already normalised by caller, but defensive guard here
#   * > _MAX_RELATIVE_PATH_LEN chars
#   * any control byte (0x00-0x1f or 0x7f); blocks NUL injection / log spam
#   * backslash; paths must be POSIX, never Windows-style
#   * leading slash; looks like an absolute path
#   * any segment exactly equal to `..` — that's the path-traversal vector.
#     Inside-segment `..` (e.g., `v1.0..final.txt`) is fine; only a complete
#     `..` segment between separators escapes the upload directory.
_MAX_RELATIVE_PATH_LEN = 512
_CONTROL_BYTES = re.compile(r"[\x00-\x1f\x7f]")

# Single source of truth for the aggregate-cap failed-row reason — the
# string is emitted from two arms of the upload loop (the loop-top
# already-tripped check, and the mid-loop tripping check) and must stay
# byte-identical: the FE summary modal groups failed rows by reason
# string equality, so a near-miss diverged copy renders two near-
# identical lines (S5 same shape).
_AGGREGATE_CAP_REASON = (
    f"aggregate upload size exceeds the {MAX_AGGREGATE_UPLOAD_BYTES // (1024 * 1024)} MB limit"
)


def _is_valid_relative_path(rel_path: str) -> bool:
    """Return True if *rel_path* is safe to persist as a document path.

    See module-level commentary on the denylist rationale.
    """
    if not rel_path or len(rel_path) > _MAX_RELATIVE_PATH_LEN:
        return False
    if rel_path.startswith("/"):
        return False
    if "\\" in rel_path:
        return False
    if _CONTROL_BYTES.search(rel_path):
        return False
    # `..` only as a complete segment is traversal.
    if any(seg == ".." for seg in rel_path.split("/")):
        return False
    return True


def _is_valid_filename(filename: str) -> bool:
    """Return True if *filename* is safe to persist as ``meta["filename"]``.

    Mirrors the relative-path denylist (I6) but rejects any path
    separator (filenames are not paths) and the bare `..` traversal
    vocabulary. Length is bounded by the schema's ``max_length=512``;
    callers should also strip whitespace before this check.

    Defends two surfaces:
      1. The filename is rendered into the per-query LLM context (I5
         channel `_build_doc_context`); control bytes / newlines /
         boundary-marker characters allow prompt injection.
      2. The filename surfaces in HTTP Content-Disposition headers and
         UI labels; control bytes break headers and confuse layouts.
    """
    if not filename:
        return False
    if "/" in filename or "\\" in filename:
        return False
    if _CONTROL_BYTES.search(filename):
        return False
    if filename == "..":
        return False
    return True


# Allow / for old-style arXiv IDs (e.g. cs/9808001v1), but block .. traversal.
# This regex IS the path-traversal defence in this module: handlers below use
# `state.uploads_dir / doc_id` directly without further sanitisation, so the
# negative-lookahead `(?!.*\.\.)` is what stops `..` from escaping the dir.
# Loosen the regex only with a matching defence (e.g. routing every path
# through a safe_path helper).
_SAFE_ID_RE = re.compile(r"^(?!.*\.\.)[a-zA-Z0-9][a-zA-Z0-9._/-]*$")


def _validate_doc_id(doc_id: str) -> None:
    """Raise 400 if *doc_id* contains path-traversal characters."""
    if not _SAFE_ID_RE.match(doc_id):
        raise HTTPException(400, f"Invalid document id: {doc_id!r}")


def _make_project_id(filename: str) -> str:
    """Generate project_id from filename: slugified-name-xxxxxxxxxxxx.

    The 12-hex suffix is cryptographically random (`secrets.token_hex(6)` —
    48-bit space; ~16M-name birthday threshold). The caller's allocator
    retries up to 5 times on collision; with the 48-bit space this is
    practically unreachable. The previous 32-bit suffix combined with a
    3-pick retry budget had a ~65k-name birthday threshold (I14), so
    under sustained concurrent upload load with stable filenames the
    allocator could plausibly exhaust its picks and report a spurious
    failure to the caller despite no permanent collision. An even earlier
    implementation hashed the filename plus a microsecond timestamp,
    which was deterministic enough that two calls in the same microsecond
    produced identical IDs — and the rollback path would then destroy
    the colliding pre-existing project's data.
    """
    stem = Path(filename).stem
    slug = _slugify(stem) or "document"
    return f"{slug}-{secrets.token_hex(6)}"


def _failed_row(
    filename: str,
    reason: str,
    relative_path: str | None = None,
) -> DocumentUploadResponse:
    """Build a `failed` upload-row response for partial-success uploads."""
    return DocumentUploadResponse(
        project_id="",
        filename=filename,
        status="failed",
        reason=reason,
        relative_path=relative_path,
    )


def _persist_one_upload(
    state: DocumentExplorerState,
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
    ext: str,
    rel_path: str | None,
    upload_session_id: str | None,
    topic: str | None,
) -> DocumentUploadResponse:
    """Persist a single uploaded file to disk + storage + topic.

    Synchronous: invoked via ``asyncio.to_thread`` from the upload route
    so the entire per-file disk-and-storage block (mkdir-with-retry,
    write_bytes of up to 50 MiB, extract_text, get_page_count, meta.json
    write, create_project, store_document of up to 16 MiB extracted text,
    topic add_item) runs off the event loop. Bulk uploads of up to 500
    files would otherwise starve websocket pings, RLM streams,
    document-list polls, and concurrent handlers (I2 full).

    Per-file rollback runs in-thread on any failure: if this call created
    the upload directory or the Ananta project, both are cleaned up so an
    interrupted persist doesn't strand orphan state.
    """
    upload_dir: Path | None = None
    project_id: str | None = None
    created_upload_dir = False
    created_project = False
    try:
        # Allocate an upload dir we know is fresh. The 48-bit random
        # suffix (I14) makes collisions rare; mkdir(exist_ok=False) +
        # retry-on-FileExistsError is the defence against the small
        # remaining birthday-collision risk. Five attempts is plenty
        # given the ~16M-name birthday threshold.
        for _attempt in range(5):
            project_id = _make_project_id(filename)
            upload_dir = state.uploads_dir / project_id
            try:
                upload_dir.mkdir(parents=True, exist_ok=False)
                created_upload_dir = True
                break
            except FileExistsError:
                upload_dir = None
                project_id = None
                continue
        if not created_upload_dir or upload_dir is None or project_id is None:
            return _failed_row(filename, "could not allocate a unique upload directory", rel_path)
        original_path = upload_dir / f"original{ext}"
        original_path.write_bytes(content)

        try:
            text = extract_text(original_path)
        except ValueError as exc:
            shutil.rmtree(upload_dir, ignore_errors=True)
            return _failed_row(filename, f"text extraction failed: {exc}", rel_path)

        # Page count is purely informational; a failure here must not
        # abort the upload — the file already extracted cleanly.
        try:
            page_count = get_page_count(original_path)
        except Exception:
            _logger.exception("get_page_count failed for %r", filename)
            page_count = None

        meta: dict[str, Any] = {
            "filename": filename,
            "content_type": content_type or "application/octet-stream",
            "size": len(content),
            "upload_date": datetime.now(UTC).isoformat(),
            "page_count": page_count,
        }
        if rel_path is not None:
            meta["relative_path"] = rel_path
        if upload_session_id is not None:
            meta["upload_session_id"] = upload_session_id
        (upload_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        state.ananta.create_project(project_id)
        created_project = True
        doc_metadata: dict[str, str | int | float | bool] = {
            "filename": filename,
            "size": len(content),
        }
        if rel_path is not None:
            doc_metadata["relative_path"] = rel_path
        if upload_session_id is not None:
            doc_metadata["upload_session_id"] = upload_session_id
        doc = ParsedDocument(
            name=filename,
            content=text,
            format=ext.lstrip(".") or "txt",
            metadata=doc_metadata,
            char_count=len(text),
        )
        state.ananta.storage.store_document(project_id, doc)

        if topic:
            state.topic_mgr.add_item(topic, project_id)

        return DocumentUploadResponse(
            project_id=project_id,
            filename=filename,
            status="created",
            relative_path=rel_path,
        )
    except Exception as exc:
        # Per-file rollback: clean up only this file's state. Critical
        # (C4): only rmtree the upload_dir if THIS request created it.
        if upload_dir is not None and created_upload_dir:
            shutil.rmtree(upload_dir, ignore_errors=True)
        # Critical (I6): only delete the project if THIS upload created
        # it. If create_project raised on an id collision, the project
        # belongs to someone else — deleting it would destroy unrelated data.
        if project_id is not None and created_project:
            try:
                state.topic_mgr.remove_item_from_all(project_id)
            except Exception:
                pass  # Best-effort cleanup — original error takes priority
            try:
                state.ananta.delete_project(project_id)
            except Exception:
                pass  # Best-effort cleanup — original error takes priority
        # Log the original exception server-side; return a generic reason
        # to avoid leaking filesystem paths or dependency error details.
        _logger.exception("Unexpected error processing upload %r: %s", filename, exc)
        return _failed_row(filename, "unexpected upload error", rel_path)


def _read_upload_meta(uploads_dir: Path, project_id: str) -> dict[str, Any] | None:
    """Read upload metadata for a document, or None if missing/corrupt."""
    meta_path = uploads_dir / project_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _build_doc_info(uploads_dir: Path, project_id: str) -> DocumentInfo | None:
    """Build a DocumentInfo from upload metadata, or None if not available."""
    meta = _read_upload_meta(uploads_dir, project_id)
    if meta is None:
        return None
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


def _resolve_doc_project_ids(
    state: DocumentExplorerState,
    topic_name: str,
) -> list[str]:
    """Resolve a topic name to project IDs for trace aggregation.

    Falls back to all projects if the topic has no docs or doesn't exist.
    """
    try:
        items = state.topic_mgr.list_items(topic_name)
        if items:
            return items
    except ValueError:
        pass  # Topic doesn't exist; fall back to all projects
    return state.ananta.list_projects()


def _list_doc_trace_files(
    state: DocumentExplorerState,
    project_id: str,
) -> list[Path]:
    """List trace files from Ananta storage."""
    return state.ananta.storage.list_traces(project_id)


def _create_document_router(state: DocumentExplorerState) -> APIRouter:
    """Create API router for document management routes."""
    router = APIRouter(prefix="/api")

    @router.get("/documents")
    def list_documents() -> list[DocumentInfo]:
        project_ids = state.ananta.list_projects()
        result: list[DocumentInfo] = []
        for pid in project_ids:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.get("/documents/uncategorized")
    def list_uncategorized() -> list[DocumentInfo]:
        all_ids = state.ananta.list_projects()
        uncategorized = state.topic_mgr.list_uncategorized(all_ids)
        result: list[DocumentInfo] = []
        for pid in uncategorized:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.get("/topics/{name}/items")
    def list_topic_items(name: str) -> list[DocumentInfo]:
        try:
            doc_ids = state.topic_mgr.list_items(name)
        except ValueError as e:
            raise HTTPException(404, f"Topic '{name}' not found") from e
        result: list[DocumentInfo] = []
        for pid in doc_ids:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.post("/documents/upload")
    async def upload_documents(
        files: list[UploadFile],
        topic: str | None = Form(default=None),
        relative_path: list[str] | None = Form(default=None),
        upload_session_id: str | None = Form(default=None),
    ) -> list[DocumentUploadResponse]:
        # DoS guard: cap the number of files per request so a large client
        # submission can't enqueue tens of thousands of synchronous filesystem
        # ops on the event loop. Frontend folder-walk enforces the same cap
        # client-side, but any direct API caller (or click-folder picker) can
        # otherwise bypass it.
        if len(files) > MAX_FOLDER_FILES:
            raise HTTPException(
                413,
                f"Upload exceeds the {MAX_FOLDER_FILES}-file per-request limit",
            )
        # If relative_path is supplied, the client MUST send one entry per
        # file. A short array silently substituted None per-file before, so
        # the wrong path was persisted with no error to the caller (I2).
        if relative_path is not None and len(relative_path) != len(files):
            raise HTTPException(
                422,
                "relative_path length must match files length",
            )
        # Validate topic name up-front so we fail before creating any
        # files or projects — avoids orphaned data on invalid topics.
        # Topic-validation is still all-or-nothing; only per-file work is
        # partial-success.
        # Track whether THIS request created the topic so we can roll it
        # back on full failure (S6). A topic the user explicitly created
        # via POST /api/topics — or a topic that already carries items
        # from a previous upload — must NOT be deleted.
        topic_existed_before = bool(topic) and topic in state.topic_mgr.list_topics()
        if topic:
            try:
                state.topic_mgr.create(topic)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

        results: list[DocumentUploadResponse] = []
        total_bytes = 0
        aggregate_cap_reached = False

        for idx, file in enumerate(files):
            if not file.filename:
                # Honour the partial-success contract: emit a row for every
                # input file rather than silently dropping unnamed ones.
                results.append(_failed_row("(unnamed)", "missing filename"))
                continue

            rel_path = (
                relative_path[idx]
                if relative_path is not None and idx < len(relative_path)
                else None
            )
            # Validate per-file (I10): unbounded user input was persisted
            # verbatim to meta.json — disk-fill DoS via giant strings, plus a
            # latent prompt-injection / path-traversal surface. Treat the
            # empty string as "absent" (forms send empty string, not null).
            if rel_path == "":
                rel_path = None
            if rel_path is not None and not _is_valid_relative_path(rel_path):
                results.append(_failed_row(file.filename or "(unnamed)", "invalid relative_path"))
                continue

            # Once the aggregate cap is breached, every remaining file gets a
            # failed row so the caller can reconcile the request count. We
            # don't break — direct API callers benefit from a row per file.
            if aggregate_cap_reached:
                results.append(_failed_row(file.filename, _AGGREGATE_CAP_REASON, rel_path))
                continue

            # Reject filenames with control bytes / path separators / `..`
            # before reading the body (I5 defense + I6 mirror at upload).
            # The filename is rendered into the per-query LLM context
            # unwrapped via _build_doc_context — newlines / boundary-marker
            # punctuation in a filename let an attacker inject content past
            # the `--- Document: ... ---` marker and into the highest-trust
            # user-message position.
            if not _is_valid_filename(file.filename):
                results.append(_failed_row(file.filename, "invalid filename", rel_path))
                continue

            # Validate extension before reading body — only needs filename,
            # avoids allocating memory for files we'll reject anyway.
            ext = Path(file.filename).suffix.lower()
            if not is_supported_extension(file.filename):
                # Path.suffix is empty for dotfiles (".env") and
                # extensionless names ("Makefile"). Surface the filename
                # so the client renders an actionable reason instead of
                # a naked trailing colon.
                descriptor = ext if ext else f"{file.filename} (no extension)"
                results.append(
                    _failed_row(file.filename, f"unsupported file type: {descriptor}", rel_path)
                )
                continue

            # Cap read to avoid memory exhaustion from oversized uploads.
            # Reason text matches the FE folder-walk skip reason verbatim
            # (S5): the summary modal groups failed rows by string equality,
            # so a near-miss diverged copy renders two near-identical lines.
            content = await file.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                results.append(
                    _failed_row(
                        file.filename,
                        f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                        rel_path,
                    )
                )
                continue

            total_bytes += len(content)
            if total_bytes > MAX_AGGREGATE_UPLOAD_BYTES:
                # Aggregate cap reached: respect the partial-success
                # contract by emitting a failed row for this file (and
                # all remaining files via the loop-top check above)
                # instead of raising 413 mid-loop and stranding earlier
                # successes (C1).
                aggregate_cap_reached = True
                results.append(_failed_row(file.filename, _AGGREGATE_CAP_REASON, rel_path))
                continue

            # Dispatch the entire per-file disk-and-storage block off the
            # event loop in a single thread (I2 full). The previous I2 fix
            # only wrapped extract_text and get_page_count; the remaining
            # sync ops (mkdir, write_bytes of up to 50 MiB, meta.json
            # write, create_project, store_document of up to 16 MiB
            # extracted text, topic_mgr.add_item) still ran on the loop.
            row = await asyncio.to_thread(
                _persist_one_upload,
                state,
                filename=file.filename,
                content_type=file.content_type,
                content=content,
                ext=ext,
                rel_path=rel_path,
                upload_session_id=upload_session_id,
                topic=topic,
            )
            results.append(row)

        # If we auto-created the topic for this request and not a single
        # file got persisted, roll it back so the user is not left with
        # a label-less stub in the sidebar (S6).
        if topic and not topic_existed_before:
            any_created = any(r.status == "created" for r in results)
            if not any_created:
                try:
                    state.topic_mgr.delete(topic)
                except ValueError:
                    # Already gone (e.g. a concurrent caller raced ahead).
                    pass

        return results

    @router.get("/documents/{doc_id}")
    def get_document(doc_id: str) -> DocumentInfo:
        _validate_doc_id(doc_id)
        info = _build_doc_info(state.uploads_dir, doc_id)
        if info is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")
        return info

    @router.get("/documents/{doc_id}/topics")
    def get_document_topics(doc_id: str) -> list[str]:
        _validate_doc_id(doc_id)
        return state.topic_mgr.find_topics_for_item(doc_id)

    @router.delete("/documents/{doc_id}")
    def delete_document(doc_id: str) -> dict[str, str]:
        _validate_doc_id(doc_id)
        # 404 for unknown ids (I13). Without this, the route returned a
        # confident "deleted" for any id, masking caller bugs that rely on
        # error signalling and contradicting the get/rename routes' 404s.
        upload_dir = state.uploads_dir / doc_id
        if not upload_dir.exists() and _read_upload_meta(state.uploads_dir, doc_id) is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")

        # Order matters (I4): delete the source-of-truth Ananta project FIRST.
        # If a later step fails (storage IO error, lock contention, race with
        # another delete), the project is already gone from
        # state.ananta.list_projects() so we never strand a silent permanent
        # orphan. Topic refs and upload files are best-effort below — failures
        # there leave at most stale references that other code paths and a
        # routine sweep can mop up, never a project that re-appears in the
        # list with no metadata.
        state.ananta.delete_project(doc_id)
        # Best-effort: remove topic refs. A failure here logs server-side
        # but does not bubble — the source-of-truth deletion already
        # succeeded, so the user-facing list endpoints will hide the
        # document on the next refresh.
        try:
            state.topic_mgr.remove_item_from_all(doc_id)
        except Exception:
            _logger.exception(
                "delete_document: topic_mgr.remove_item_from_all failed for %r",
                doc_id,
            )
        # Best-effort: remove upload files.
        if upload_dir.exists():
            try:
                shutil.rmtree(upload_dir)
            except Exception:
                _logger.exception("delete_document: shutil.rmtree failed for %r", doc_id)
        return {"status": "deleted", "project_id": doc_id}

    @router.patch("/documents/{doc_id:path}")
    def rename_document(doc_id: str, body: DocumentRename) -> DocumentInfo:
        _validate_doc_id(doc_id)
        new_name = body.new_name.strip()
        if not new_name:
            raise HTTPException(422, "new_name must not be empty or whitespace")
        if not _is_valid_filename(new_name):
            raise HTTPException(
                422,
                "new_name must not contain control bytes, '/', '\\', or be '..'",
            )
        meta = _read_upload_meta(state.uploads_dir, doc_id)
        if meta is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")
        meta["filename"] = new_name
        meta_path = state.uploads_dir / doc_id / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        info = _build_doc_info(state.uploads_dir, doc_id)
        # Just-written meta.json must be readable; if not, treat as 500.
        if info is None:
            raise HTTPException(500, f"Failed to read metadata for '{doc_id}' after rename")
        return info

    @router.get("/documents/{doc_id}/download")
    def download_document(doc_id: str) -> FileResponse:
        _validate_doc_id(doc_id)
        upload_dir = state.uploads_dir / doc_id
        if not upload_dir.exists():
            raise HTTPException(404, f"Document '{doc_id}' not found")
        meta = _read_upload_meta(state.uploads_dir, doc_id)
        filename = meta.get("filename", "download") if meta else "download"
        # Derive exact path from the stored filename's extension when
        # available; fall back to a directory scan for legacy uploads.
        ext = Path(filename).suffix if meta else ""
        original_path = upload_dir / f"original{ext}" if ext else None
        if original_path is None or not original_path.exists():
            originals = sorted(f for f in upload_dir.iterdir() if f.name.startswith("original"))
            if not originals:
                raise HTTPException(404, f"Original file not found for '{doc_id}'")
            original_path = originals[0]
        # Sanitize filename to prevent Content-Disposition header injection
        safe_filename = re.sub(r'["\r\n;]', "_", filename)
        return FileResponse(original_path, filename=safe_filename)

    return router


def create_api(state: DocumentExplorerState) -> FastAPI:
    """Create the document explorer FastAPI application."""
    doc_router = _create_document_router(state)
    item_router = create_item_router(state.topic_mgr)
    shared_router = create_shared_router(
        state,
        get_session=lambda s, name: get_topic_session(s, name),
        resolve_project_ids=lambda s, name: _resolve_doc_project_ids(s, name),
        list_trace_files=lambda s, pid: _list_doc_trace_files(s, pid),
        include_topic_crud=False,
        include_per_topic_history=True,
        include_context_budget=True,
    )
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    return create_app(
        state,
        title="Ananta Document Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[doc_router, item_router, shared_router],
    )
