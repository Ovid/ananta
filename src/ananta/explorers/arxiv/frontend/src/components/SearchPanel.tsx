import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { showToast } from '@ananta/shared-ui'
import type { SearchResult } from '../types'

interface SearchPanelProps {
  activeTopic: string | null
  onClose: () => void
  onPapersChanged: () => void
  onDownloadStarted?: (taskId: string) => void
}

type Tab = 'arxiv' | 'local'

export default function SearchPanel({ activeTopic, onClose, onPapersChanged, onDownloadStarted }: SearchPanelProps) {
  const [tab, setTab] = useState<Tab>('arxiv')
  const [query, setQuery] = useState('')
  const [author, setAuthor] = useState('')
  const [category, setCategory] = useState('')
  const [sortBy, setSortBy] = useState('relevance')
  const [showFilters, setShowFilters] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [start, setStart] = useState(0)
  const [hasSearched, setHasSearched] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addProgress, setAddProgress] = useState({ current: 0, total: 0 })
  const [addComplete, setAddComplete] = useState<string | null>(null)
  const addCompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clean up timer on unmount
  useEffect(() => () => {
    if (addCompleteTimer.current) clearTimeout(addCompleteTimer.current)
  }, [])

  const searchArxiv = async (newStart = 0) => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const data = await api.search({
        q: query, author: author || undefined, category: category || undefined,
        sort_by: sortBy, start: newStart,
      })
      if (newStart === 0) {
        setResults(data)
      } else {
        setResults(prev => [...prev, ...data])
      }
      setStart(newStart)
    } catch {
      showToast('Search failed. arXiv may be unreachable.', 'error')
    }
    setHasSearched(true)
    setLoading(false)
  }

  const searchLocal = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const data = await api.papers.search(query)
      setResults(data)
    } catch {
      showToast('Local search failed', 'error')
    }
    setHasSearched(true)
    setLoading(false)
  }

  const handleSearch = () => {
    setSelected(new Set())
    if (tab === 'arxiv') searchArxiv(0)
    else searchLocal()
  }

  const toggleSelect = (arxivId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(arxivId)) next.delete(arxivId)
      else next.add(arxivId)
      return next
    })
  }

  const addSelected = async () => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
    const ids = Array.from(selected)
    setAdding(true)
    setAddProgress({ current: 0, total: ids.length })
    for (let i = 0; i < ids.length; i++) {
      const arxivId = ids[i]
      const topics = [activeTopic]
      try {
        const result = await api.papers.add(arxivId, topics)
        if (result.task_id && onDownloadStarted) {
          onDownloadStarted(result.task_id)
        }
        // Update in_topics on the result card so it shows the tag immediately
        setResults(prev => prev.map(r =>
          r.arxiv_id === arxivId && !r.in_topics.includes(activeTopic!)
            ? { ...r, in_topics: [...r.in_topics, activeTopic!] }
            : r
        ))
      } catch (e) {
        showToast(e instanceof Error ? e.message : `Failed to add ${arxivId}`, 'error')
      }
      setAddProgress({ current: i + 1, total: ids.length })
    }
    setAdding(false)
    const msg = `Added ${ids.length} paper${ids.length > 1 ? 's' : ''}`
    setAddComplete(msg)
    if (addCompleteTimer.current) clearTimeout(addCompleteTimer.current)
    addCompleteTimer.current = setTimeout(() => setAddComplete(null), 2000)
    setSelected(new Set())
    onPapersChanged()
  }

  return (
    <aside className="w-80 border-l border-border bg-surface-1 flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex gap-2">
          <button
            onClick={() => { setTab('arxiv'); setResults([]); setHasSearched(false) }}
            className={`text-xs px-2 py-1 rounded ${tab === 'arxiv' ? 'bg-accent/10 text-accent' : 'text-text-dim hover:text-text-secondary'}`}
          >
            arXiv
          </button>
          <button
            onClick={() => { setTab('local'); setResults([]); setHasSearched(false) }}
            className={`text-xs px-2 py-1 rounded ${tab === 'local' ? 'bg-accent/10 text-accent' : 'text-text-dim hover:text-text-secondary'}`}
          >
            My Papers
          </button>
        </div>
        <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-xs">
          &times;
        </button>
      </div>

      {/* Search input */}
      <div className="px-3 py-2 border-b border-border">
        <div className="flex gap-1">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSearch() }}
            placeholder={tab === 'arxiv' ? 'Search arXiv...' : 'Search my papers...'}
            className="flex-1 bg-surface-2 border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-accent"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-2 py-1 bg-accent text-surface-0 rounded text-xs disabled:opacity-50"
          >
            {loading ? '...' : 'Go'}
          </button>
        </div>

        {/* Filters (arXiv only) */}
        {tab === 'arxiv' && (
          <>
            <button
              onClick={() => setShowFilters(f => !f)}
              className="text-[10px] text-text-dim mt-1 hover:text-text-secondary"
            >
              {showFilters ? 'Hide filters' : 'Filters'}
            </button>
            {showFilters && (
              <div className="flex flex-col gap-1 mt-1 text-xs">
                <input value={author} onChange={e => setAuthor(e.target.value)} placeholder="Author" className="bg-surface-2 border border-border rounded px-2 py-1 text-text-primary focus:outline-none" />
                <input value={category} onChange={e => setCategory(e.target.value)} placeholder="Category (e.g. q-bio.PE)" className="bg-surface-2 border border-border rounded px-2 py-1 text-text-primary focus:outline-none" />
                <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="bg-surface-2 border border-border rounded px-2 py-1 text-text-primary focus:outline-none">
                  <option value="relevance">Relevance</option>
                  <option value="lastUpdatedDate">Date</option>
                  <option value="submittedDate">Submitted</option>
                </select>
              </div>
            )}
          </>
        )}
      </div>

      {/* All / None */}
      {results.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1 text-[10px] text-text-dim border-b border-border">
          <button
            className="hover:text-accent"
            onClick={() => setSelected(new Set(results.map(r => r.arxiv_id)))}
          >All</button>
          <span>/</span>
          <button
            className="hover:text-accent"
            onClick={() => setSelected(new Set())}
          >None</button>
          {selected.size > 0 && (
            <span className="ml-auto text-text-secondary">{selected.size} selected</span>
          )}
        </div>
      )}

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {hasSearched && !loading && results.length === 0 && (
          <div className="px-3 py-6 text-center text-sm text-text-dim">
            No results found
          </div>
        )}
        {results.map(r => (
          <div
            key={r.arxiv_id}
            className={`flex items-start gap-2 px-3 py-2 border-b border-border text-xs cursor-pointer transition-colors ${
              selected.has(r.arxiv_id) ? 'bg-accent-dim' : 'hover:bg-surface-2'
            }`}
            onClick={() => toggleSelect(r.arxiv_id)}
          >
            <input
              type="checkbox"
              checked={selected.has(r.arxiv_id)}
              onChange={() => toggleSelect(r.arxiv_id)}
              onClick={e => e.stopPropagation()}
              className="shrink-0 mt-1 accent-accent"
            />
            <div className="min-w-0">
              <div className="font-medium text-text-primary text-sm leading-tight line-clamp-2">{r.title}</div>
              <div className="text-text-dim mt-0.5">{r.authors.slice(0, 3).join(', ')}{r.authors.length > 3 ? ' ...' : ''}</div>
              <div className="flex items-center gap-2 mt-1 text-text-dim font-mono">
                <span>{r.arxiv_id}</span>
                <span>{r.category}</span>
                <span>{r.date}</span>
              </div>
              {r.in_topics.length > 0 && (
                <div className="mt-1 flex gap-1 flex-wrap">
                  {r.in_topics.map(t => (
                    <span key={t} className="bg-green/10 text-green px-1 rounded text-[10px]">{t}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      {adding && (
        <div className="px-3 py-2 border-t border-border">
          <div className="flex items-center justify-between text-[10px] text-text-dim mb-1">
            <span>Adding papers...</span>
            <span>{addProgress.current}/{addProgress.total}</span>
          </div>
          <div className="w-full h-1.5 bg-surface-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all duration-300"
              style={{ width: `${addProgress.total > 0 ? (addProgress.current / addProgress.total) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Completion message */}
      {!adding && addComplete && (
        <div className="px-3 py-2 border-t border-border">
          <div className="flex items-center justify-between text-[10px] text-green mb-1">
            <span>{addComplete}</span>
          </div>
          <div className="w-full h-1.5 bg-surface-2 rounded-full overflow-hidden">
            <div className="h-full bg-green rounded-full w-full" />
          </div>
        </div>
      )}

      {/* Actions */}
      {!adding && (selected.size > 0 || (tab === 'arxiv' && results.length > 0)) && (
        <div className="px-3 py-2 border-t border-border flex items-center gap-2">
          {selected.size > 0 && (
            <button onClick={addSelected} className="px-3 py-1 bg-accent text-surface-0 rounded text-xs">
              Add {selected.size} paper{selected.size > 1 ? 's' : ''}
            </button>
          )}
          {tab === 'arxiv' && results.length > 0 && (
            <button
              onClick={() => searchArxiv(start + 10)}
              disabled={loading}
              className="px-3 py-1 border border-border text-text-secondary rounded text-xs hover:bg-surface-2 disabled:opacity-50"
            >
              Load more
            </button>
          )}
        </div>
      )}
    </aside>
  )
}
