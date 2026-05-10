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

# Per-file extracted-text cap (16 MB). The 50 MB upload cap bounds the on-
# disk file but a heavily-compressed `.xlsx` / `.pptx` / `.docx` / `.pdf`
# can unpack to hundreds of MB of plain text — a decompression-bomb DoS
# reachable by any caller with upload access. Capping at extraction time
# (a) bounds in-process memory and the on-disk document store, and
# (b) reduces attacker-controlled text in the RLM context. 16 MiB is well
# above any plausible legitimate document and well below where the LLM
# context window would meaningfully use the bytes anyway.
MAX_EXTRACTED_TEXT_BYTES = 16 * 1024 * 1024
