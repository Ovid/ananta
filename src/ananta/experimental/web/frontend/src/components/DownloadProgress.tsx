import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

interface PaperStatus {
  arxiv_id: string
  status: string
}

interface DownloadProgressProps {
  taskIds: string[]
  onComplete: (taskId: string) => void
}

export default function DownloadProgress({ taskIds, onComplete }: DownloadProgressProps) {
  const [papers, setPapers] = useState<PaperStatus[]>([])
  const [dismissed, setDismissed] = useState(false)
  const completedRef = useRef(new Set<string>())
  const completedPapersRef = useRef(new Map<string, PaperStatus[]>())

  // Reset dismissed state when new tasks arrive
  const prevTaskIdsRef = useRef(new Set<string>())
  useEffect(() => {
    const hasNewTask = taskIds.some(id => !prevTaskIdsRef.current.has(id))
    if (hasNewTask) {
      setDismissed(false)
    }
    prevTaskIdsRef.current = new Set(taskIds)
  }, [taskIds])

  const poll = useCallback(async () => {
    const allPapers: PaperStatus[] = []
    // Include cached papers from previously completed tasks
    for (const cached of completedPapersRef.current.values()) {
      allPapers.push(...cached)
    }
    for (const taskId of taskIds) {
      if (completedRef.current.has(taskId)) continue
      try {
        const data = await api.papers.taskStatus(taskId)
        allPapers.push(...data.papers)
        const allDone = data.papers.every(
          (p: PaperStatus) => p.status === 'complete' || p.status === 'error'
        )
        if (allDone) {
          completedRef.current.add(taskId)
          completedPapersRef.current.set(taskId, data.papers)
          onComplete(taskId)
        }
      } catch {
        // Task may have been cleaned up
      }
    }
    setPapers(allPapers)
  }, [taskIds, onComplete])

  useEffect(() => {
    if (taskIds.length === 0) return

    // Poll immediately, then every 2 seconds
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [taskIds, poll])

  // Clean up completed refs when taskIds change
  useEffect(() => {
    const current = new Set(taskIds)
    for (const id of completedRef.current) {
      if (!current.has(id)) {
        completedRef.current.delete(id)
        completedPapersRef.current.delete(id)
      }
    }
  }, [taskIds])

  if (taskIds.length === 0 || papers.length === 0 || dismissed) return null

  const completed = papers.filter(p => p.status === 'complete').length
  const errored = papers.filter(p => p.status === 'error').length
  const total = papers.length
  const done = completed + errored
  const inProgress = papers.find(p => p.status === 'downloading')
  const phase = inProgress
    ? `Downloading ${inProgress.arxiv_id}...`
    : done === total
      ? 'Complete'
      : 'Waiting...'

  // When nothing is complete yet but downloads are active, pulse the bar
  const isIndeterminate = done === 0 && total > 0
  const barPercent = total > 0 ? (done / total) * 100 : 0
  const barClass = done === total
    ? 'bg-green'
    : isIndeterminate
      ? 'bg-accent animate-progress-slide'
      : 'bg-accent'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[700px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Downloading Papers</h2>
          <button
            onClick={() => setDismissed(true)}
            className="text-text-dim hover:text-text-secondary text-lg leading-none"
          >
            &times;
          </button>
        </div>

        {/* Content */}
        <div className="px-4 py-3">
          <div className="text-center py-8">
            <div className="text-sm text-text-secondary mb-2">
              {done}/{total} &mdash; {phase}
            </div>
            <div className="w-full bg-surface-2 rounded-full h-2 overflow-hidden">
              <div
                data-testid="download-bar-fill"
                className={`h-2 rounded-full transition-all ${barClass}`}
                style={{ width: isIndeterminate ? '30%' : `${barPercent}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
