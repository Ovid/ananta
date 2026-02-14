import { useState, useEffect } from 'react'
import { showToast } from './Toast'
import type { TraceFull, TraceStep } from '../types'

interface TraceViewerProps {
  topicName: string
  traceId: string
  onClose: () => void
  /** Fetch full trace data. Receives (topicName, traceId) and returns TraceFull. */
  fetchTrace: (topicName: string, traceId: string) => Promise<TraceFull>
}

const stepTypeColors: Record<string, string> = {
  code_generated: 'bg-blue-500',
  code_output: 'bg-green',
  final_answer: 'bg-accent',
  subcall_request: 'bg-amber',
  subcall_response: 'bg-amber',
  verification: 'bg-purple-500',
  semantic_verification: 'bg-purple-500',
}

export default function TraceViewer({ topicName, traceId, onClose, fetchTrace }: TraceViewerProps) {
  const [trace, setTrace] = useState<TraceFull | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())
  const [allExpanded, setAllExpanded] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchTrace(topicName, traceId).then(data => {
      setTrace(data)
      setLoading(false)
    }).catch(() => {
      showToast('Failed to load trace', 'error')
      setLoading(false)
    })
  }, [topicName, traceId, fetchTrace])

  const toggleStep = (idx: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    if (allExpanded) {
      setExpandedSteps(new Set())
    } else {
      setExpandedSteps(new Set(trace?.steps.map((_, i) => i) || []))
    }
    setAllExpanded(!allExpanded)
  }

  return (
    <div className="fixed inset-y-0 right-0 w-[480px] bg-surface-1 border-l border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">Trace Viewer</h2>
        <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg">&times;</button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-text-dim text-sm">Loading...</div>
      ) : trace ? (
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Summary */}
          <div className="px-4 py-3 border-b border-border text-xs text-text-secondary space-y-1">
            <div className="text-sm text-text-primary font-medium">{trace.question}</div>
            <div className="flex gap-4 text-text-dim font-mono">
              <span>Model: {trace.model}</span>
              <span>Iterations: {trace.total_iterations}</span>
              <span>Status: <span className={trace.status === 'success' ? 'text-green' : 'text-red'}>{trace.status}</span></span>
            </div>
            <div className="flex gap-4 text-text-dim font-mono">
              <span>Duration: {(trace.duration_ms / 1000).toFixed(1)}s</span>
              <span>Tokens: {Object.values(trace.total_tokens).reduce((a, b) => a + b, 0)}</span>
            </div>
            {trace.document_ids && trace.document_ids.length > 0 && (
              <div className="text-text-dim font-mono">
                <span>Documents: </span>
                {trace.document_ids.map((id, i) => (
                  <span key={id}>{i > 0 ? ', ' : ''}{id}</span>
                ))}
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="px-4 py-2 border-b border-border flex gap-2">
            <button onClick={toggleAll} className="text-xs text-accent hover:underline">
              {allExpanded ? 'Collapse all' : 'Expand all'}
            </button>
          </div>

          {/* Steps timeline */}
          <div className="px-4 py-2">
            {trace.steps.map((step, idx) => (
              <StepCard
                key={idx}
                step={step}
                index={idx}
                expanded={expandedSteps.has(idx)}
                onToggle={() => toggleStep(idx)}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-text-dim text-sm">Trace not found.</div>
      )}
    </div>
  )
}

function StepCard({ step, index, expanded, onToggle }: { step: TraceStep; index: number; expanded: boolean; onToggle: () => void }) {
  const dotColor = stepTypeColors[step.step_type] || 'bg-text-dim'

  return (
    <div className="relative pl-5 pb-3">
      {/* Timeline line */}
      <div className="absolute left-[7px] top-3 bottom-0 w-px bg-border" />
      {/* Dot */}
      <div className={`absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 border-surface-1 ${dotColor}`} />

      <button onClick={onToggle} className="w-full text-left">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono text-text-dim">#{index}</span>
          <span className="font-medium text-text-secondary">{step.step_type}</span>
          <span className="text-text-dim">iter {step.iteration}</span>
          {step.tokens_used != null && (
            <span className="text-text-dim">{step.tokens_used} tok</span>
          )}
          <span className="text-text-dim ml-auto">{expanded ? '\u25BC' : '\u25B6'}</span>
        </div>
      </button>

      {expanded && (
        <div className="mt-1 bg-surface-2 border border-border rounded p-2 text-xs font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap">
          {step.content}
        </div>
      )}
    </div>
  )
}
