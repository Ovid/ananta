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

    // Intentionally do not pass `signal` to fetch: cancel is between-batches,
    // not mid-batch. The current batch always completes (or errors) before we
    // honour the abort. Do not "fix" this without revisiting the design.
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
