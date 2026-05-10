import type { WalkedFile } from '../lib/folder-walk'

export interface UploadRow {
  project_id: string
  filename: string
  status: 'created' | 'failed'
  reason?: string
  // Echoed back from the server so the FE summary can disambiguate
  // duplicate-named files when the user uploaded a multi-folder structure
  // (I4). Server emits `null` for unset values (Pydantic `string | None`);
  // older server builds that pre-date the field omit it entirely. Both
  // shapes coalesce to falsy at every consumer site (S7).
  relative_path?: string | null
}

// Carries the rows accumulated across earlier successful batches when a
// later batch fails. Without this, throwing a plain Error stranded earlier
// rows in a closure local — the hook then surfaced "0 ingested" even though
// batches 1..K-1 were durably committed server-side (C2).
export class BatchUploadError extends Error {
  constructor(message: string, public readonly partial: UploadRow[]) {
    super(message)
    this.name = 'BatchUploadError'
  }
}

export async function formatHttpError(res: Response): Promise<string> {
  // Prefer FastAPI's structured ``{ detail: string | object }`` body when
  // present so the user sees the server's actual reason. Fall back to a
  // status-class-specific phrase, then the bare status. Avoids the
  // previous cryptic "upload failed: 413" (I9).
  let detail = ''
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail)) {
      // FastAPI's automatic Pydantic-validation 422 returns an array of
      // {loc, msg, type} objects (S2). Joining the msg fields gives the
      // user a friendly summary instead of a JSON blob like
      //   [{"loc":["body","new_name"],"msg":"...","type":"..."}]
      const msgs = (body.detail as Array<{ msg?: unknown }>)
        .map(e => (typeof e?.msg === 'string' ? e.msg : ''))
        .filter(Boolean)
      detail = msgs.join('; ')
    }
    // Other non-string detail shapes (e.g., {error: "..."}) intentionally
    // fall through to the status-class phrase below — the previous
    // JSON.stringify produced unfriendly toasts and the friendly fallback
    // was unreachable.
  } catch {
    // Non-JSON body — common for proxy-injected 502/504 pages.
  }
  if (detail) return `upload failed: ${detail}`
  if (res.status === 413) return 'upload failed: files too large for this request'
  if (res.status === 422) return 'upload failed: server rejected the request as invalid'
  if (res.status >= 500) return `upload failed: server error (${res.status})`
  return `upload failed: ${res.status}`
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
    // Emit a "batch starting" progress event BEFORE the network round-trip
    // so the modal label advances to "batch K of N" while batch K is
    // actually in flight (I5). Without this, onProgress only fires on the
    // post-batch line below and the label trails one batch behind reality
    // for batches 2+ (the hook's initial setState covers batch 1 only).
    onProgress(completed, total, i + 1, batches.length)
    const form = new FormData()
    for (const wf of batch) {
      form.append('files', wf.file, wf.file.name)
      form.append('relative_path', wf.relativePath)
    }
    form.append('topic', topic)
    form.append('upload_session_id', sessionId)

    // Intentionally do not pass `signal` to fetch: cancel is between-batches,
    // not mid-batch. The current batch always completes (or errors) before we
    // honour the abort. Do not "fix" this without revisiting the design.
    //
    // Every error path through this block must surface as BatchUploadError
    // carrying `all` (I2). A network drop, DNS failure, or malformed JSON
    // body that bubbles up as a plain TypeError/SyntaxError otherwise
    // strands the rows from earlier successful batches: the hook's
    // `instanceof BatchUploadError` guard goes false and the user sees
    // "0 ingested" even though batches 1..K-1 have already been durably
    // committed server-side.
    let rows: UploadRow[]
    try {
      const res = await fetch('/api/documents/upload', { method: 'POST', body: form })
      if (!res.ok) {
        throw new BatchUploadError(await formatHttpError(res), all)
      }
      rows = (await res.json()) as UploadRow[]
    } catch (err) {
      if (err instanceof BatchUploadError) throw err
      const message = err instanceof Error ? err.message : String(err)
      throw new BatchUploadError(`upload failed: ${message}`, all)
    }
    all.push(...rows)
    completed += batch.length
    onProgress(completed, total, i + 1, batches.length)
  }

  return all
}
