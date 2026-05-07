"""Document explorer API.

Provides document upload, CRUD, and topic-document reference routes.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

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

# Allow / for old-style arXiv IDs (e.g. cs/9808001v1), but block .. traversal.
# safe_path() provides the real path-traversal defence; this is belt-and-suspenders.
_SAFE_ID_RE = re.compile(r"^(?!.*\.\.)[a-zA-Z0-9][a-zA-Z0-9._/-]*$")


def _validate_doc_id(doc_id: str) -> None:
    """Raise 400 if *doc_id* contains path-traversal characters."""
    if not _SAFE_ID_RE.match(doc_id):
        raise HTTPException(400, f"Invalid document id: {doc_id!r}")


def _make_project_id(filename: str) -> str:
    """Generate project_id from filename: slugified-name-xxxxxxxx.

    The 8-hex suffix is cryptographically random (`secrets.token_hex(4)`) so
    two uploads with the same filename in fast succession are vanishingly
    unlikely to collide. A previous implementation hashed the filename plus
    a microsecond timestamp, which was deterministic enough that two calls
    in the same microsecond produced identical IDs — and the rollback path
    would then destroy the colliding pre-existing project's data.
    """
    stem = Path(filename).stem
    slug = _slugify(stem) or "document"
    return f"{slug}-{secrets.token_hex(4)}"


def _failed_row(filename: str, reason: str) -> DocumentUploadResponse:
    """Build a `failed` upload-row response for partial-success uploads."""
    return DocumentUploadResponse(
        project_id="",
        filename=filename,
        status="failed",
        reason=reason,
    )


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
        # Validate topic name up-front so we fail before creating any
        # files or projects — avoids orphaned data on invalid topics.
        # Topic-validation is still all-or-nothing; only per-file work is
        # partial-success.
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
            created_project = False
            try:
                # Validate extension before reading body — only needs filename,
                # avoids allocating memory for files we'll reject anyway.
                ext = Path(file.filename).suffix.lower()
                if not is_supported_extension(file.filename):
                    results.append(_failed_row(file.filename, f"unsupported file type: {ext}"))
                    continue

                # Cap read to avoid memory exhaustion from oversized uploads.
                content = await file.read(MAX_UPLOAD_BYTES + 1)
                if len(content) > MAX_UPLOAD_BYTES:
                    results.append(
                        _failed_row(
                            file.filename,
                            f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                        )
                    )
                    continue

                total_bytes += len(content)
                if total_bytes > MAX_AGGREGATE_UPLOAD_BYTES:
                    # Aggregate cap remains a hard 413 — frontend chunking
                    # should ensure this is never reached in practice.
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

                # Extract text
                try:
                    text = extract_text(original_path)
                except ValueError as exc:
                    shutil.rmtree(upload_dir, ignore_errors=True)
                    results.append(_failed_row(file.filename, f"text extraction failed: {exc}"))
                    continue

                # Compute page/sheet/slide count where applicable
                page_count = get_page_count(original_path)

                # Save upload metadata
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
                created_project = True
                doc_metadata: dict[str, str | int | float | bool] = {
                    "filename": file.filename,
                    "size": len(content),
                }
                if rel_path is not None:
                    doc_metadata["relative_path"] = rel_path
                doc = ParsedDocument(
                    name=file.filename,
                    content=text,
                    format=ext.lstrip(".") or "txt",
                    metadata=doc_metadata,
                    char_count=len(text),
                )
                state.ananta.storage.store_document(project_id, doc)

                if topic:
                    state.topic_mgr.add_item(topic, project_id)

                results.append(
                    DocumentUploadResponse(
                        project_id=project_id,
                        filename=file.filename,
                        status="created",
                    )
                )
            except HTTPException:
                raise  # 413 aggregate cap propagates as before
            except Exception as exc:
                # Per-file rollback: clean up only this file's state.
                if upload_dir is not None:
                    shutil.rmtree(upload_dir, ignore_errors=True)
                # Critical (I6): only delete the project if THIS upload created
                # it. If create_project raised (e.g., ProjectExistsError on an
                # id collision), the project belongs to someone else — deleting
                # it would destroy unrelated data.
                if project_id is not None and created_project:
                    try:
                        state.topic_mgr.remove_item_from_all(project_id)
                    except Exception:
                        pass  # Best-effort cleanup — original error takes priority
                    try:
                        state.ananta.delete_project(project_id)
                    except Exception:
                        pass  # Best-effort cleanup — original error takes priority
                # Log the original exception server-side for diagnosis but
                # return a generic reason to the client — raw exception text
                # can leak internal details (filesystem paths, dependency
                # errors, stack-trace fragments).
                _logger.exception(
                    "Unexpected error processing upload %r: %s", file.filename, exc
                )
                results.append(_failed_row(file.filename, "unexpected upload error"))

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
        state.topic_mgr.remove_item_from_all(doc_id)
        # Remove upload files
        upload_dir = state.uploads_dir / doc_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        # Remove Ananta project
        state.ananta.delete_project(doc_id)
        return {"status": "deleted", "project_id": doc_id}

    @router.patch("/documents/{doc_id:path}")
    def rename_document(doc_id: str, body: DocumentRename) -> DocumentInfo:
        _validate_doc_id(doc_id)
        new_name = body.new_name.strip()
        if not new_name:
            raise HTTPException(422, "new_name must not be empty or whitespace")
        meta = _read_upload_meta(state.uploads_dir, doc_id)
        if meta is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")
        meta["filename"] = new_name
        meta_path = state.uploads_dir / doc_id / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        return DocumentInfo(
            project_id=doc_id,
            filename=meta.get("filename", ""),
            content_type=meta.get("content_type", ""),
            size=meta.get("size", 0),
            upload_date=meta.get("upload_date", ""),
            page_count=meta.get("page_count"),
            relative_path=meta.get("relative_path"),
            upload_session_id=meta.get("upload_session_id"),
        )

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
