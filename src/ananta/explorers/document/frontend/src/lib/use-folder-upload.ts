import { useCallback, useState } from 'react'
import {
  walkEntries,
  filterFiles,
  partitionIntoBatches,
  TARGET_BATCH_BYTES,
  type WalkedFile,
  type SkippedFile,
} from './folder-walk'
import { uploadFolderInBatches, type UploadRow } from '../api/documents'
import type { ModalState } from '../components/FolderUploadModal'

// Mirrors the FolderUploadInput discriminated union from UploadArea.tsx.
// Re-defined locally rather than imported to keep this hook decoupled from the
// component layer; structural typing means both shapes are interchangeable.
export type FolderInput =
  | { kind: 'entries'; entries: FileSystemEntry[]; rootName: string }
  | { kind: 'walked'; files: WalkedFile[]; rootName: string }

export function useFolderUpload() {
  const [state, setState] = useState<ModalState | null>(null)
  const [pending, setPending] = useState<{ accepted: WalkedFile[]; topic: string; skipped: SkippedFile[] } | null>(null)
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
    // O(n^2) but n <= 500 (MAX_FOLDER_FILES); acceptable.
    const acceptedWalked: WalkedFile[] = walked.filter(w => accepted.includes(w.file))
    const skippedTyped: SkippedFile[] = skipped
    setState({ kind: 'preflight', accepted: acceptedWalked, skipped: skippedTyped, targetTopic: topic })
    setPending({ accepted: acceptedWalked, topic, skipped: skippedTyped })
  }, [])

  const confirm = useCallback(async () => {
    if (!pending) return
    const { accepted, topic, skipped: preflightSkipped } = pending
    const batches = partitionIntoBatches(accepted, TARGET_BATCH_BYTES)
    const total = accepted.length
    const sessionId = crypto.randomUUID()
    const ctl = new AbortController()
    setAbortCtl(ctl)
    setState({ kind: 'progress', total, completed: 0, currentBatch: 0, totalBatches: batches.length })
    let rows: UploadRow[] = []
    try {
      rows = await uploadFolderInBatches(
        batches,
        topic,
        sessionId,
        (completed, totalCnt, currentBatch, totalBatches) => {
          setState({ kind: 'progress', total: totalCnt, completed, currentBatch, totalBatches })
        },
        ctl.signal,
      )
    } finally {
      setAbortCtl(null)
    }
    const ingested = rows.filter(r => r.status === 'created').length
    const failed = rows
      .filter(r => r.status === 'failed')
      .map(r => ({ name: r.filename, reason: r.reason ?? 'failed' }))
    // Carry pre-flight skipped rows through to the summary so the user sees
    // every file that did not get ingested, not just upload-time failures.
    setState({
      kind: 'summary',
      ingested,
      failed,
      skipped: preflightSkipped.map(s => ({ name: s.file.name, reason: s.reason })),
    })
    setPending(null)
  }, [pending])

  const cancel = useCallback(() => {
    abortCtl?.abort()
    setState(null)
    setPending(null)
  }, [abortCtl])

  return { state, start, confirm, cancel }
}
