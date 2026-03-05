# Document Explorer Design

## Overview

A new web tool for uploading, organizing, and querying documents using the
Shesha RLM. Follows the same shared infrastructure as arXiv Explorer and Code
Explorer. Users upload files, group them into topics, and ask questions via the
chat interface.

## Architecture

- **Backend:** `src/shesha/experimental/document_explorer/` — FastAPI app using
  shared infrastructure (`app_factory`, `shared_router`)
- **Frontend:** `src/shesha/experimental/document_explorer/frontend/` — React
  app using `@shesha/shared-ui`
- **Docker:** `document-explorer/` — multi-stage Dockerfile + docker-compose
- **Entry point:** `shesha-document-explorer` CLI command, default port 8003

## Storage Model

One Shesha project per uploaded document (same pattern as code explorer repos).
Topics hold project ID references, enabling cross-topic sharing without
duplication.

```
~/.shesha/document-explorer/
  shesha_data/
    projects/
      {doc-project-id}/        # One per uploaded file
        _meta.json
        docs/
          content.json         # ParsedDocument (extracted text)
        traces/
  topics/
    {slug}/
      topic.json               # {"name": "...", "docs": ["doc-project-id-1", ...]}
      conversation.json        # Per-topic chat history
  uploads/
    {doc-project-id}/
      original.pdf             # Original uploaded file
      meta.json                # filename, content_type, size, upload_date
```

### Project ID format

Slugified original filename + short hash, e.g. `quarterly-report-a3f2`.

## Document Ingestion

### Upload flow

1. User drags/picks file(s) in the web UI, optionally selects a target topic
2. `POST /api/documents/upload` receives multipart form data
3. Backend generates `doc-project-id` from slugified filename + short hash
4. Original file saved to `uploads/{doc-project-id}/`
5. Text extracted based on file extension -> `ParsedDocument` stored in Shesha
   project
6. If topic specified, reference added to `topic.json`

### Text extraction

| Format     | Extension(s)                                           | Library        |
|------------|--------------------------------------------------------|----------------|
| Plain text | `.txt`, `.md`, `.csv`, `.log`, `.json`, `.yaml`, `.xml`, `.html` | Built-in `open()` (UTF-8 with fallback) |
| PDF        | `.pdf`                                                 | `pdfplumber`   |
| Word       | `.docx`                                                | `python-docx`  |
| PowerPoint | `.pptx`                                                | `python-pptx`  |
| Excel      | `.xlsx`                                                | `openpyxl`     |
| RTF        | `.rtf`                                                 | `striprtf`     |

A single `extract_text(path, content_type) -> str` dispatcher selects the
extractor by extension. Unsupported files get a clear error at upload time.

### ParsedDocument metadata

Original filename, file type, file size, upload date, and page/sheet/slide
count where applicable.

## Topic Manager

`DocumentTopicManager` mirrors `CodeExplorerTopicManager`:

```
topics/{slug}/
  topic.json          # {"name": "ML Research", "docs": ["quarterly-report-a3f2", ...]}
  conversation.json   # Per-topic chat history
```

### Methods

- `create(name)` / `delete(name)` / `rename(old, new)` — topic CRUD
- `add_doc(topic, doc_project_id)` — add reference (idempotent)
- `remove_doc(topic, doc_project_id)` — remove reference only
- `list_docs(topic)` -> `list[str]` of project IDs
- `list_all_docs()` -> unique project IDs across all topics
- `list_uncategorized(all_ids)` -> documents not in any topic
- `find_topics_for_doc(doc_project_id)` -> which topics reference this doc
- `remove_doc_from_all(doc_project_id)` — cleanup on document deletion

### Sharing semantics

- Adding an existing document to a second topic appends its project ID to that
  topic's `topic.json` — no file copying.
- Deleting a document from a topic removes only the reference.
- Fully deleting a document removes the project, the upload, and all topic
  references.

## API Routes

### Document-specific

| Method   | Path                               | Purpose                              |
|----------|------------------------------------|--------------------------------------|
| `POST`   | `/api/documents/upload`            | Upload file(s), optionally to topic  |
| `GET`    | `/api/documents`                   | List all documents                   |
| `GET`    | `/api/documents/uncategorized`     | Documents not in any topic           |
| `GET`    | `/api/documents/{doc_id}`          | Document metadata                    |
| `GET`    | `/api/documents/{doc_id}/download` | Download original file               |
| `DELETE` | `/api/documents/{doc_id}`          | Delete document from system          |

### Topic-document cross-references

| Method   | Path                                        | Purpose                    |
|----------|---------------------------------------------|----------------------------|
| `GET`    | `/api/topics/{name}/documents`              | List documents in topic    |
| `POST`   | `/api/topics/{name}/documents/{doc_id}`     | Add existing doc to topic  |
| `DELETE` | `/api/topics/{name}/documents/{doc_id}`     | Remove doc from topic      |

### Shared routes

Topic CRUD, traces, history, model, context budget — all from
`create_shared_router()`.

## WebSocket Handler

Custom handler (code explorer pattern) since queries load documents from
multiple projects:

1. Receive query with `document_ids` (project IDs) and `topic_name`
2. Load `ParsedDocument` from Shesha storage for each project ID
3. Build context with document metadata (filename, type)
4. Use per-topic session for conversation history
5. Execute RLM query with all loaded documents
6. Save exchange to topic's conversation history

## Frontend

### Shared components (from `@shesha/shared-ui`)

AppShell, Header, ChatArea, StatusBar, TraceViewer, TopicSidebar,
ToastContainer, ConfirmDialog.

### New components

| Component        | Purpose                                                        |
|------------------|----------------------------------------------------------------|
| `UploadArea`     | Drag-and-drop zone + file picker, upload progress per file     |
| `DocumentDetail` | Modal: metadata, download original, topic membership, delete   |
| `DocumentItem`   | Sidebar row: file-type icon, filename, size sublabel           |

### State management

- `useAppState` hook for theme, WS, model, tokens, sidebar, topics, traces
- `selectedDocs: Set<string>` — checked document project IDs for querying
- `allDocs: DocumentInfo[]` — fetched from `/api/documents`

### Key interactions

1. Select topic -> sidebar loads documents via `/api/topics/{name}/documents`
2. Upload files -> drag onto sidebar or click upload button
3. Click document -> `DocumentDetail` modal
4. Select documents + ask question -> query sent with selected project IDs
5. From `DocumentDetail`, add document to other topics or remove

No search panel — upload is the only ingestion path.

## New Dependencies

Added to `pyproject.toml` under a `[document-explorer]` extra:

| Package            | Purpose                        |
|--------------------|--------------------------------|
| `python-docx`      | Word .docx extraction          |
| `python-pptx`      | PowerPoint .pptx extraction    |
| `openpyxl`         | Excel .xlsx extraction         |
| `striprtf`         | RTF extraction                 |
| `python-multipart` | FastAPI file upload support    |

`pdfplumber` is already a dependency.

### pyproject.toml entry point

```toml
shesha-document-explorer = "shesha.experimental.document_explorer.__main__:main"
```

## Docker

Same multi-stage pattern as other explorers:

```
document-explorer/
  Dockerfile
  docker-compose.yml
  document-explorer.sh
```

Port 8003. Volume maps to `/data` which includes `shesha_data/`, `topics/`,
and `uploads/`.

## Out of Scope (POC)

- OCR for scanned PDFs/images
- Document versioning (re-upload creates new document)
- Bulk import from filesystem
- Full-text search panel
- In-browser document preview
- Chunking/embedding/vector DB
- Max file size enforcement
