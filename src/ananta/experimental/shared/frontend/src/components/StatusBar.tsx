import type { ContextBudget } from '../types'

interface StatusBarProps {
  topicName: string | null
  modelName: string
  tokens: { prompt: number; completion: number; total: number }
  budget: ContextBudget | null
  phase: string
  onModelClick: () => void
  documentBytes?: number
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const budgetColors: Record<string, string> = {
  green: 'text-green',
  amber: 'text-amber',
  red: 'text-red',
}

const phaseColors: Record<string, string> = {
  Ready: 'bg-green',
  Starting: 'bg-amber',
  Running: 'bg-amber',
  Complete: 'bg-green',
  Error: 'bg-red',
}

export default function StatusBar({
  topicName,
  modelName,
  tokens,
  budget,
  phase,
  onModelClick,
  documentBytes,
}: StatusBarProps) {
  const budgetColor = budget ? budgetColors[budget.level] || 'text-text-dim' : 'text-text-dim'
  const dotColor = phaseColors[phase] || 'bg-text-dim'

  return (
    <footer className="h-7 border-t border-border bg-surface-1 flex items-center px-4 text-[11px] text-text-dim font-mono shrink-0">
      <span className="mr-4">
        Project: <span className="text-text-secondary">{topicName || '\u2014'}</span>
      </span>
      <span className="mr-4">
        Model:{' '}
        <button
          onClick={onModelClick}
          className="text-text-secondary hover:text-accent transition-colors cursor-pointer"
        >
          {modelName}
        </button>
      </span>
      <span className="mr-4">
        Tokens: <span className="text-text-secondary">{tokens.total}</span>{' '}
        (prompt: {tokens.prompt}, completion: {tokens.completion})
      </span>
      {budget && (
        <span className={`mr-4 ${budgetColor}`}>
          Context: {budget.percentage.toFixed(0)}%
        </span>
      )}
      {documentBytes != null && documentBytes > 0 && (
        <span className="mr-4">
          Docs: <span className="text-text-secondary">{formatBytes(documentBytes)}</span>
        </span>
      )}
      <div className="flex-1" />
      <span className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${dotColor}`} />
        Phase: <span className="text-text-secondary">{phase}</span>
      </span>
    </footer>
  )
}
