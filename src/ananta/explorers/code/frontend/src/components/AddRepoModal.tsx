import { useState, useEffect, useRef } from 'react'

interface AddRepoModalProps {
  topics: string[]
  onSubmit: (url: string, topic?: string) => void
  onClose: () => void
}

export default function AddRepoModal({ topics, onSubmit, onClose }: AddRepoModalProps) {
  const [url, setUrl] = useState('')
  const [selectedTopic, setSelectedTopic] = useState('')
  const backdropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleSubmit = () => {
    if (!url.trim()) return
    onSubmit(url.trim(), selectedTopic || undefined)
  }

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) {
      onClose()
    }
  }

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-surface-1 border border-border rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-bold text-text-primary mb-4">Add Repository</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-text-secondary mb-1">Repository URL</label>
            <input
              autoFocus
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="w-full bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="block text-sm text-text-secondary mb-1">Topic (optional)</label>
            <select
              value={selectedTopic}
              onChange={e => setSelectedTopic(e.target.value)}
              className="w-full bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="">{'\u2014 No topic \u2014'}</option>
              {topics.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!url.trim()}
            className="px-4 py-2 bg-accent text-surface-0 rounded text-sm font-medium hover:bg-accent/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  )
}
