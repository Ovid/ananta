import { useCallback, useRef, useState } from 'react'
import {
  walkEntries,
  filterFiles,
  partitionIntoBatches,
  FolderCapExceededError,
  MAX_FOLDER_FILES,
  TARGET_BATCH_BYTES,
  type WalkedFile,
  type SkippedFile,
} from './folder-walk'
import { uploadFolderInBatches, BatchUploadError, type UploadRow } from '../api/documents'
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
  // Re-entry guard for the (potentially slow) walkEntries phase (I10). The
  // abortCtl-based guard only kicks in after confirm() runs; until then a
  // second drop could race the first walk and clobber its preflight state.
  // walkingRef is set eagerly at the top of start() and cleared in finally.
  const walkingRef = useRef(false)
  // Increments whenever uploaded rows have been committed server-side and the
  // caller should refresh its document list. Bumps on summary AND on cancel-
  // mid-flight (the in-flight batch always commits before cancel is honoured —
  // see api/documents.ts), but not on cancel from preflight (nothing committed).
  const [commitVersion, setCommitVersion] = useState(0)

  const start = useCallback(async (input: FolderInput, topic: string) => {
    // Refuse a second start while an upload is in flight or another walk
    // is still resolving (I10). The abortCtl-based guard only kicks in
    // after confirm() runs; without walkingRef, a second drop during the
    // first folder's slow walkEntries could clobber state/pending and the
    // late-arriving first walk would then overwrite the second's preflight.
    if (abortCtlRef.current || walkingRef.current) return
    walkingRef.current = true
    try {
      let walked: WalkedFile[]
      if (input.kind === 'entries') {
        try {
          walked = await walkEntries(input.entries, input.rootName)
        } catch (err) {
          // Only the hard cap-exceeded refusal short-circuits to summary.
          // walkEntries swallows per-file / per-subtree errors itself, but
          // an unrelated readAllEntries rejection at the top level would
          // otherwise be misreported as "folder exceeds the N-file limit".
          // Discriminate by class, not by message text (I6).
          if (!(err instanceof FolderCapExceededError)) throw err
          setState({
            kind: 'summary',
            ingested: 0,
            failed: [],
            skipped: [{ name: input.rootName, reason: err.message }],
          })
          return
        }
      } else {
        walked = input.files
      }
      const { accepted, skipped } = filterFiles(walked)
      // Count the cap against the *accepted* set only — drag-drop's walkEntries
      // does the same (Inline 5). Otherwise a folder of mostly unsupported
      // assets (e.g. a git repo with images) trips the cap on click but
      // succeeds on drop (I7). Drop path: walkEntries already raised on cap,
      // so accepted.length <= MAX_FOLDER_FILES here. Click path: enforce now.
      if (accepted.length > MAX_FOLDER_FILES) {
        setState({
          kind: 'summary',
          ingested: 0,
          failed: [],
          skipped: [{ name: input.rootName, reason: `folder exceeds the ${MAX_FOLDER_FILES}-file limit` }],
        })
        return
      }
      setState({ kind: 'preflight', accepted, skipped, targetTopic: topic })
      setPending({ accepted, topic, skipped })
    } finally {
      walkingRef.current = false
    }
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
      // Merge any rows accumulated by earlier batches before this one
      // failed so the summary reflects the durably-committed work (C2).
      if (err instanceof BatchUploadError) {
        rows = err.partial
      }
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
    // Disambiguate duplicate-named files in the summary (I4): when the
    // server echoes a relative_path that differs from the bare filename,
    // prefer it so two README.md files from different subfolders don't
    // present identically. For pre-flight skipped, do the same with the
    // local relativePath we already have on every WalkedFile.
    const summaryName = (filename: string, relPath?: string): string =>
      relPath && relPath !== filename ? relPath : filename
    const failed = rows
      .filter(r => r.status === 'failed')
      .map(r => ({ name: summaryName(r.filename, r.relative_path), reason: r.reason ?? 'failed' }))
    if (uploadError) {
      failed.push({ name: 'upload', reason: uploadError.message })
    }
    // Carry pre-flight skipped rows through to the summary so the user sees
    // every file that did not get ingested, not just upload-time failures.
    setState({
      kind: 'summary',
      ingested,
      failed,
      skipped: preflightSkipped.map(s => ({ name: summaryName(s.file.name, s.relativePath), reason: s.reason })),
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
