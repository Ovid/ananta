import { useMemo, useState } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import type { PaperInfo } from '../types'
import { ConfirmDialog } from '@shesha/shared-ui'

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function renderTextCommands(html: string): string {
  return html
    .replace(/\\emph\{([^}]+)\}/g, '<em>$1</em>')
    .replace(/\\textit\{([^}]+)\}/g, '<em>$1</em>')
    .replace(/\\textbf\{([^}]+)\}/g, '<strong>$1</strong>')
    .replace(/\\texttt\{([^}]+)\}/g, '<code>$1</code>')
}

function renderLatex(text: string): string {
  // Escape HTML first, then convert LaTeX text commands and math
  return renderTextCommands(escapeHtml(text))
    .replace(/\$\$([^$]+)\$\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex, { displayMode: true, throwOnError: false })
      } catch {
        return `$$${tex}$$`
      }
    })
    .replace(/\$([^$]+)\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex, { displayMode: false, throwOnError: false })
      } catch {
        return `$${tex}$`
      }
    })
}

interface PaperDetailProps {
  paper: PaperInfo | null
  topicName: string
  onRemove: (arxivId: string) => void
  onClose: () => void
}

export default function PaperDetail({ paper, topicName, onRemove, onClose }: PaperDetailProps) {
  const [confirmRemove, setConfirmRemove] = useState(false)

  const renderedAbstract = useMemo(
    () => paper ? renderLatex(paper.abstract) : '',
    [paper?.abstract],
  )
  const renderedTitle = useMemo(
    () => paper ? renderLatex(paper.title) : '',
    [paper?.title],
  )

  if (!paper) return null

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Top bar with Back button */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-surface-1">
        <button
          onClick={onClose}
          className="text-sm text-text-secondary hover:text-accent transition-colors"
        >
          &larr; Back
        </button>
        <span className="text-xs text-text-dim font-mono">{paper.arxiv_id}</span>
      </div>

      {/* Paper content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
        <h1
          className="text-xl font-semibold text-text-primary leading-tight"
          dangerouslySetInnerHTML={{ __html: renderedTitle }}
        />
        <p className="text-sm text-text-secondary mt-2">
          {paper.authors.join(', ')}
        </p>
        <div className="flex items-center gap-3 mt-3 text-xs text-text-dim font-mono">
          <span>{paper.category}</span>
          <span>{paper.date}</span>
          <a
            href={paper.arxiv_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            View on arXiv
          </a>
        </div>
        <div
          className="mt-6 text-sm text-text-secondary leading-relaxed"
          dangerouslySetInnerHTML={{ __html: renderedAbstract }}
        />

        {/* Actions */}
        <div className="mt-8 flex gap-3">
          <button
            onClick={() => setConfirmRemove(true)}
            className="px-3 py-1.5 text-xs text-red border border-red/30 rounded hover:bg-red/10 transition-colors"
          >
            Remove from topic
          </button>
        </div>
      </div>

      {confirmRemove && (
        <ConfirmDialog
          title="Remove paper"
          message={`Remove "${paper.title}" from "${topicName}"?`}
          confirmLabel="Remove"
          destructive
          onConfirm={() => {
            setConfirmRemove(false)
            onRemove(paper.arxiv_id)
          }}
          onCancel={() => setConfirmRemove(false)}
        />
      )}
    </div>
  )
}
