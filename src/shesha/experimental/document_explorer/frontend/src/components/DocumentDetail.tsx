import { useEffect, useRef, type MouseEvent } from 'react'
import type { DocumentInfo } from '../types'

interface DocumentDetailProps {
  doc: DocumentInfo
  topics: string[]
  docTopics: string[]
  onClose: () => void
  onDelete: (projectId: string) => void
  onAddToTopic: (projectId: string, topic: string) => void
  onRemoveFromTopic: (projectId: string, topic: string) => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DocumentDetail({
  doc, topics, docTopics, onClose, onDelete, onAddToTopic, onRemoveFromTopic,
}: DocumentDetailProps) {
  const backdropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target === backdropRef.current) onClose()
  }

  const otherTopics = topics.filter(t => !docTopics.includes(t))

  return (
    <div ref={backdropRef} className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={handleBackdropClick}>
      <div className="bg-surface-1 border border-border rounded-lg shadow-xl w-full max-w-md p-6 max-h-[80vh] overflow-y-auto">
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-bold text-text-primary truncate pr-4">{doc.filename}</h2>
          <button onClick={onClose} aria-label="Close" className="text-text-dim hover:text-text-primary shrink-0">&times;</button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between"><span className="text-text-secondary">Type</span><span className="text-text-primary">{doc.content_type}</span></div>
          <div className="flex justify-between"><span className="text-text-secondary">Size</span><span className="text-text-primary">{formatSize(doc.size)}</span></div>
          <div className="flex justify-between"><span className="text-text-secondary">Uploaded</span><span className="text-text-primary">{new Date(doc.upload_date).toLocaleDateString()}</span></div>
          {doc.page_count != null && (
            <div className="flex justify-between"><span className="text-text-secondary">Pages</span><span className="text-text-primary">{doc.page_count}</span></div>
          )}
        </div>

        <div className="mt-4 flex gap-2">
          <a
            href={`/api/documents/${encodeURIComponent(doc.project_id)}/download`}
            className="px-3 py-1.5 bg-accent text-surface-0 rounded text-sm hover:bg-accent/90 transition-colors"
            download
          >
            Download
          </a>
          <button
            onClick={() => onDelete(doc.project_id)}
            className="px-3 py-1.5 bg-red text-white rounded text-sm hover:bg-red/90 transition-colors"
          >
            Delete
          </button>
        </div>

        {docTopics.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-text-secondary mb-2">In topics:</h3>
            <div className="flex flex-wrap gap-1">
              {docTopics.map(t => (
                <span key={t} className="inline-flex items-center gap-1 px-2 py-0.5 bg-surface-2 rounded text-xs text-text-primary">
                  {t}
                  <button onClick={() => onRemoveFromTopic(doc.project_id, t)} className="text-text-dim hover:text-red">&times;</button>
                </span>
              ))}
            </div>
          </div>
        )}

        {otherTopics.length > 0 && (
          <div className="mt-3">
            <h3 className="text-sm font-medium text-text-secondary mb-2">Add to topic:</h3>
            <div className="flex flex-wrap gap-1">
              {otherTopics.map(t => (
                <button
                  key={t}
                  onClick={() => onAddToTopic(doc.project_id, t)}
                  className="px-2 py-0.5 border border-border rounded text-xs text-text-secondary hover:border-accent hover:text-accent transition-colors"
                >
                  + {t}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
