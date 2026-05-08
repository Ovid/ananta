import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { WalkedFile, SkippedFile } from '../lib/folder-walk'
import { SOFT_WARN_FOLDER_FILES } from '../lib/folder-walk'

export type ModalState =
  | { kind: 'preflight'; accepted: WalkedFile[]; skipped: SkippedFile[]; targetTopic: string }
  | { kind: 'progress'; total: number; completed: number; currentBatch: number; totalBatches: number }
  | { kind: 'summary'; ingested: number; failed: { name: string; reason: string }[]; skipped: { name: string; reason: string }[] }

interface Props {
  state: ModalState
  // `onContinue` is the primary action handler. In `preflight` it means "Continue",
  // in `summary` it means "Close". The `progress` view does not use it.
  onContinue: () => void
  onCancel: () => void
}

export default function FolderUploadModal({ state, onContinue, onCancel }: Props) {
  if (state.kind === 'preflight') {
    return <PreflightView state={state} onContinue={onContinue} onCancel={onCancel} />
  }
  if (state.kind === 'progress') {
    return <ProgressView state={state} onCancel={onCancel} />
  }
  if (state.kind === 'summary') {
    return <SummaryView state={state} onContinue={onContinue} />
  }
  return null
}

function ModalShell({
  ariaLabel,
  children,
}: {
  ariaLabel: string
  children: ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-label={ariaLabel}
        className="w-full max-w-md rounded-lg border border-border bg-bg-primary p-4 text-sm text-text-primary shadow-lg"
      >
        {children}
      </div>
    </div>
  )
}

function PreflightView({
  state,
  onContinue,
  onCancel,
}: {
  state: Extract<ModalState, { kind: 'preflight' }>
  onContinue: () => void
  onCancel: () => void
}) {
  // Local guard against double-clicks (I7): even though useFolderUpload's
  // confirm() now no-ops when an upload is in flight, disabling the button
  // immediately on click prevents a second event from queuing at all and
  // gives the user clear visual feedback.
  const [confirming, setConfirming] = useState(false)
  const totalBytes = useMemo(
    () => state.accepted.reduce((sum, f) => sum + f.file.size, 0),
    [state.accepted],
  )
  const skippedByReason = useMemo(() => {
    const m = new Map<string, number>()
    for (const s of state.skipped) m.set(s.reason, (m.get(s.reason) ?? 0) + 1)
    return [...m.entries()]
  }, [state.skipped])
  const showWarning = state.accepted.length > SOFT_WARN_FOLDER_FILES

  return (
    <ModalShell ariaLabel="Folder upload preview">
      <h2 className="text-base font-semibold">Upload to: {state.targetTopic}</h2>
      <p className="mt-2 text-text-secondary">
        {state.accepted.length} files ({formatBytes(totalBytes)})
      </p>
      {showWarning && (
        <p role="alert" className="mt-2 rounded border border-warning bg-warning-dim p-2 text-warning">
          This will add {state.accepted.length} files. Continue?
        </p>
      )}
      {skippedByReason.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-dim">Skipped</h3>
          <ul className="mt-1 space-y-1 text-text-secondary">
            {skippedByReason.map(([reason, count]) => (
              <li key={reason}>
                {count} {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-dim hover:border-text-dim hover:text-text-secondary cursor-pointer"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={confirming || state.accepted.length === 0}
          onClick={() => {
            if (confirming || state.accepted.length === 0) return
            setConfirming(true)
            onContinue()
          }}
          className="rounded-lg border border-accent bg-accent-dim px-3 py-1.5 text-xs text-accent hover:bg-accent hover:text-bg-primary cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
        >
          Continue
        </button>
      </div>
    </ModalShell>
  )
}

function ProgressView({
  state,
  onCancel,
}: {
  state: Extract<ModalState, { kind: 'progress' }>
  onCancel: () => void
}) {
  const pct = state.total > 0 ? Math.round((state.completed / state.total) * 100) : 0
  return (
    <ModalShell ariaLabel="Folder upload progress">
      <h2 className="text-base font-semibold">Uploading folder</h2>
      <p className="mt-2 text-text-secondary">
        Uploading {state.completed} of {state.total} files… (batch {state.currentBatch} of {state.totalBatches})
      </p>
      <progress
        value={pct}
        max={100}
        className="mt-3 h-2 w-full overflow-hidden rounded bg-bg-secondary [&::-webkit-progress-bar]:bg-bg-secondary [&::-webkit-progress-value]:bg-accent [&::-moz-progress-bar]:bg-accent"
      />
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-dim hover:border-text-dim hover:text-text-secondary cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </ModalShell>
  )
}

function SummaryView({
  state,
  onContinue,
}: {
  state: Extract<ModalState, { kind: 'summary' }>
  // Re-purposed as the "Close" handler in this view; see top-level prop comment.
  onContinue: () => void
}) {
  return (
    <ModalShell ariaLabel="Folder upload summary">
      <h2 className="text-base font-semibold">Upload complete</h2>
      <p className="mt-2 text-text-secondary">{state.ingested} ingested</p>
      {state.failed.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-dim">
            Failed ({state.failed.length})
          </h3>
          <ul className="mt-1 space-y-1 text-text-secondary">
            {state.failed.map((f, i) => (
              <li key={i}>
                <span className="font-mono text-text-primary">{f.name}</span>
                {' — '}
                {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {state.skipped.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-dim">
            Skipped ({state.skipped.length})
          </h3>
          <ul className="mt-1 space-y-1 text-text-secondary">
            {state.skipped.map((s, i) => (
              <li key={i}>
                <span className="font-mono text-text-primary">{s.name}</span>
                {' — '}
                {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onContinue}
          className="rounded-lg border border-accent bg-accent-dim px-3 py-1.5 text-xs text-accent hover:bg-accent hover:text-bg-primary cursor-pointer"
        >
          Close
        </button>
      </div>
    </ModalShell>
  )
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
