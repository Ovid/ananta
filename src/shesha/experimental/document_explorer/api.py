"""Document explorer API.

Provides document upload, CRUD, and topic-document reference routes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from shesha.experimental.document_explorer.dependencies import (
    DocumentExplorerState,
    get_topic_session,
)
from shesha.experimental.document_explorer.extractors import (
    extract_text,
    get_page_count,
    is_supported_extension,
)
from shesha.experimental.document_explorer.schemas import (
    DocumentInfo,
    DocumentUploadResponse,
)
from shesha.experimental.document_explorer.topics import _slugify
from shesha.experimental.document_explorer.websockets import websocket_handler
from shesha.experimental.shared.app_factory import create_app
from shesha.experimental.shared.routes import create_item_router, create_shared_router
from shesha.models import ParsedDocument

# Maximum upload size per file (50 MB).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_doc_id(doc_id: str) -> None:
    """Raise 400 if *doc_id* contains path-traversal characters."""
    if not _SAFE_ID_RE.match(doc_id):
        raise HTTPException(400, f"Invalid document id: {doc_id!r}")


def _make_project_id(filename: str) -> str:
    """Generate project_id from filename: slugified-name-xxxxxxxx."""
    stem = Path(filename).stem
    slug = _slugify(stem) or "document"
    short_hash = hashlib.sha256(f"{filename}-{datetime.now(UTC).isoformat()}".encode()).hexdigest()[
        :8
    ]
    return f"{slug}-{short_hash}"


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
    return state.shesha.list_projects()


def _list_doc_trace_files(
    state: DocumentExplorerState,
    project_id: str,
) -> list[Path]:
    """List trace files from Shesha storage."""
    return state.shesha.storage.list_traces(project_id)


def _create_document_router(state: DocumentExplorerState) -> APIRouter:
    """Create API router for document management routes."""
    router = APIRouter(prefix="/api")

    @router.get("/documents")
    def list_documents() -> list[DocumentInfo]:
        project_ids = state.shesha.list_projects()
        result: list[DocumentInfo] = []
        for pid in project_ids:
            info = _build_doc_info(state.uploads_dir, pid)
            if info is not None:
                result.append(info)
        return result

    @router.get("/documents/uncategorized")
    def list_uncategorized() -> list[DocumentInfo]:
        all_ids = state.shesha.list_projects()
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
    ) -> list[DocumentUploadResponse]:
        # Validate topic name up-front so we fail before creating any
        # files or projects — avoids orphaned data on invalid topics.
        if topic:
            try:
                state.topic_mgr.create(topic)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

        results: list[DocumentUploadResponse] = []
        created_projects: list[str] = []
        created_upload_dirs: list[Path] = []
        try:
            for file in files:
                if not file.filename:
                    continue

                project_id = _make_project_id(file.filename)

                # Validate extension before reading body — only needs filename,
                # avoids allocating memory for files we'll reject anyway.
                ext = Path(file.filename).suffix.lower()
                if not is_supported_extension(file.filename):
                    raise HTTPException(422, f"Unsupported file type: {ext}")

                # Cap read to avoid memory exhaustion from oversized uploads.
                content = await file.read(MAX_UPLOAD_BYTES + 1)
                if len(content) > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        f"File '{file.filename}' exceeds the "
                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                    )

                # Save original file
                upload_dir = state.uploads_dir / project_id
                upload_dir.mkdir(parents=True, exist_ok=True)
                created_upload_dirs.append(upload_dir)

                original_path = upload_dir / f"original{ext}"
                original_path.write_bytes(content)

                # Extract text
                try:
                    text = extract_text(original_path)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc

                # Compute page/sheet/slide count where applicable
                page_count = get_page_count(original_path)

                # Save upload metadata
                meta = {
                    "filename": file.filename,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": len(content),
                    "upload_date": datetime.now(UTC).isoformat(),
                    "page_count": page_count,
                }
                (upload_dir / "meta.json").write_text(json.dumps(meta, indent=2))

                state.shesha.create_project(project_id)
                created_projects.append(project_id)
                doc = ParsedDocument(
                    name=file.filename,
                    content=text,
                    format=ext.lstrip(".") or "txt",
                    metadata={"filename": file.filename, "size": len(content)},
                    char_count=len(text),
                )
                state.shesha.storage.store_document(project_id, doc)

                if topic:
                    state.topic_mgr.add_item(topic, project_id)

                results.append(
                    DocumentUploadResponse(
                        project_id=project_id,
                        filename=file.filename,
                        status="created",
                    )
                )
        except Exception:
            # Roll back all projects and upload dirs created so far
            for pid in created_projects:
                try:
                    state.topic_mgr.remove_item_from_all(pid)
                except Exception:
                    pass  # Best-effort cleanup — original error takes priority
                try:
                    state.shesha.delete_project(pid)
                except Exception:
                    pass  # Best-effort cleanup — original error takes priority
            for udir in created_upload_dirs:
                shutil.rmtree(udir, ignore_errors=True)
            raise

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
        # Remove Shesha project
        state.shesha.delete_project(doc_id)
        return {"status": "deleted", "project_id": doc_id}

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
        title="Shesha Document Explorer",
        static_dir=frontend_dist,
        images_dir=images_dir,
        ws_handler=lambda ws: websocket_handler(ws, state),
        extra_routers=[doc_router, item_router, shared_router],
    )
