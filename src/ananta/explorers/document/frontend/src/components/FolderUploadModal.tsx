import { useMemo } from 'react'
import type { WalkedFile, SkippedFile } from '../lib/folder-walk'
import { SOFT_WARN_FOLDER_FILES } from '../lib/folder-walk'

export type ModalState =
  | { kind: 'preflight'; accepted: WalkedFile[]; skipped: SkippedFile[]; targetTopic: string }
  | { kind: 'progress'; total: number; completed: number; currentBatch: number; totalBatches: number }
  | { kind: 'summary'; ingested: number; failed: { name: string; reason: string }[]; skipped: { name: string; reason: string }[] }

interface Props {
  state: ModalState
  onContinue: () => void
  onCancel: () => void
}

export default function FolderUploadModal({ state, onContinue, onCancel }: Props) {
  if (state.kind === 'preflight') {
    return <PreflightView state={state} onContinue={onContinue} onCancel={onCancel} />
  }
  return null // progress/summary added in C5
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-label="Folder upload preview"
        className="w-full max-w-md rounded-lg border border-border bg-bg-primary p-4 text-sm text-text-primary shadow-lg"
      >
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
            onClick={onContinue}
            className="rounded-lg border border-accent bg-accent-dim px-3 py-1.5 text-xs text-accent hover:bg-accent hover:text-bg-primary cursor-pointer"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  )
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
