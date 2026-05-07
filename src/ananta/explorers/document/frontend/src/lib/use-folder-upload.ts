import { useCallback, useRef, useState } from 'react'
import {
  walkEntries,
  filterFiles,
  partitionIntoBatches,
  MAX_FOLDER_FILES,
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
  // Held in a ref rather than state so cancel() can never read a stale value.
  // Using setState here meant cancel callbacks captured between renders would
  // see whichever AbortController was committed at their definition time —
  // potentially null when an upload was in flight (S6).
  const abortCtlRef = useRef<AbortController | null>(null)
  // Increments whenever uploaded rows have been committed server-side and the
  // caller should refresh its document list. Bumps on summary AND on cancel-
  // mid-flight (the in-flight batch always commits before cancel is honoured —
  // see api/documents.ts), but not on cancel from preflight (nothing committed).
  const [commitVersion, setCommitVersion] = useState(0)

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
      // Click-folder picker: the browser hands us a flat file list, bypassing
      // walkEntries. Apply the same MAX_FOLDER_FILES cap drag-drop enforces
      // so click and drop paths agree on the limit (I3).
      if (input.files.length > MAX_FOLDER_FILES) {
        setState({
          kind: 'summary',
          ingested: 0,
          failed: [],
          skipped: [{ name: input.rootName, reason: `folder exceeds the ${MAX_FOLDER_FILES}-file limit` }],
        })
        return
      }
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
    // Re-entry guard (I7): a double-click on Continue (touch screens,
    // accessibility tools, queued events) can fire confirm twice before the
    // state transition to 'progress' commits. The second call must not start
    // a second upload — clear pending atomically by reading-then-clearing.
    if (state?.kind === 'progress' || abortCtlRef.current) return
    const { accepted, topic, skipped: preflightSkipped } = pending
    const batches = partitionIntoBatches(accepted, TARGET_BATCH_BYTES)
    const total = accepted.length
    const sessionId = crypto.randomUUID()
    const ctl = new AbortController()
    abortCtlRef.current = ctl
    // currentBatch is 1-based: batch 1 is in progress at this point. Without
    // this, the modal briefly renders "batch 0 of N" until the first
    // onProgress callback fires after batch 1 commits.
    setState({ kind: 'progress', total, completed: 0, currentBatch: 1, totalBatches: batches.length })
    let rows: UploadRow[] = []
    let uploadError: Error | null = null
    try {
      rows = await uploadFolderInBatches(
        batches,
        topic,
        sessionId,
        (completed, totalCnt, currentBatch, totalBatches) => {
          // A late progress callback can fire after the user clicked Cancel
          // (the in-flight batch completes before we honour the abort, by
          // design — see api/documents.ts). Drop it so it doesn't reanimate
          // the modal that cancel() just closed.
          if (ctl.signal.aborted) return
          setState({ kind: 'progress', total: totalCnt, completed, currentBatch, totalBatches })
        },
        ctl.signal,
      )
    } catch (err) {
      // A non-OK response (e.g., 413) or network drop bubbles out of
      // uploadFolderInBatches. Without this catch the modal would stay stuck
      // on 'progress' with no error info — only Cancel works (I4).
      uploadError = err instanceof Error ? err : new Error(String(err))
    } finally {
      // Only clear if the ref still points at our controller. If upload A is
      // cancelled and upload B starts before A's promise settles, A's finally
      // would otherwise wipe B's controller — leaving cancel() unable to
      // abort B's in-flight request (C3).
      if (abortCtlRef.current === ctl) abortCtlRef.current = null
    }
    if (ctl.signal.aborted) {
      // User cancelled mid-flight: cancel() already cleared state and bumped
      // commitVersion. Do not emit a summary — that would re-mount the modal
      // the user just closed.
      setPending(null)
      return
    }
    const ingested = rows.filter(r => r.status === 'created').length
    const failed = rows
      .filter(r => r.status === 'failed')
      .map(r => ({ name: r.filename, reason: r.reason ?? 'failed' }))
    if (uploadError) {
      failed.push({ name: 'upload', reason: uploadError.message })
    }
    // Carry pre-flight skipped rows through to the summary so the user sees
    // every file that did not get ingested, not just upload-time failures.
    setState({
      kind: 'summary',
      ingested,
      failed,
      skipped: preflightSkipped.map(s => ({ name: s.file.name, reason: s.reason })),
    })
    setPending(null)
    setCommitVersion(v => v + 1)
  }, [pending, state])

  const cancel = useCallback(() => {
    // Cancel from progress means at least one batch completed server-side
    // before we honoured the abort — bump commitVersion so the caller can
    // refresh. Cancel from preflight has nothing to refresh. Reading the
    // ref here (instead of useState) means cancel never closes over a stale
    // value of the abort controller (S6).
    const ctl = abortCtlRef.current
    if (ctl) {
      ctl.abort()
      abortCtlRef.current = null
      setCommitVersion(v => v + 1)
    }
    setState(null)
    setPending(null)
  }, [])

  return { state, start, confirm, cancel, commitVersion }
}
