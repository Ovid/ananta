import { useState, useEffect, type CSSProperties, type MouseEvent } from 'react'
import { api } from '../api/client'
import { showToast, ConfirmDialog } from '@shesha/shared-ui'
import type { TopicInfo, PaperInfo } from '../types'

interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
  refreshKey: number
  selectedPapers: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  onPaperClick: (paper: PaperInfo) => void
  onPapersLoaded: (papers: PaperInfo[]) => void
  viewingPaperId?: string | null
  style?: CSSProperties
}

export default function TopicSidebar({ activeTopic, onSelectTopic, onTopicsChange, refreshKey, selectedPapers, onSelectionChange, onPaperClick, onPapersLoaded, viewingPaperId, style }: TopicSidebarProps) {
  const [topics, setTopics] = useState<TopicInfo[]>([])
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renamingTopic, setRenamingTopic] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null)
  const [topicPapers, setTopicPapers] = useState<Record<string, PaperInfo[]>>({})
  const [deletingTopic, setDeletingTopic] = useState<string | null>(null)

  const loadTopics = async () => {
    try {
      const data = await api.topics.list()
      setTopics(data)
    } catch {
      showToast('Failed to load topics', 'error')
    }
  }

  useEffect(() => { loadTopics() }, [refreshKey])
  useEffect(() => { setTopicPapers({}) }, [refreshKey])

  // Auto-expand and load papers when active topic changes
  useEffect(() => {
    if (!activeTopic) return
    setExpandedTopic(activeTopic)
    if (!topicPapers[activeTopic]) {
      api.papers.list(activeTopic).then(papers => {
        setTopicPapers(prev => ({ ...prev, [activeTopic]: papers }))
        onPapersLoaded(papers)
      }).catch(() => {})
    } else {
      onPapersLoaded(topicPapers[activeTopic])
    }
  }, [activeTopic])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleTogglePapers = async (topicName: string, e: MouseEvent) => {
    e.stopPropagation()
    if (expandedTopic === topicName) {
      setExpandedTopic(null)
      return
    }
    setExpandedTopic(topicName)
    if (!topicPapers[topicName]) {
      try {
        const papers = await api.papers.list(topicName)
        setTopicPapers(prev => ({ ...prev, [topicName]: papers }))
        onPapersLoaded(papers)
      } catch {
        showToast('Failed to load papers', 'error')
      }
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await api.topics.create(newName.trim())
      setCreating(false)
      setNewName('')
      await loadTopics()
      onTopicsChange()
      onSelectTopic(newName.trim())
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to create topic', 'error')
    }
  }

  const handleRename = async (oldName: string) => {
    if (!renameValue.trim() || renameValue.trim() === oldName) {
      setRenamingTopic(null)
      return
    }
    try {
      await api.topics.rename(oldName, renameValue.trim())
      setRenamingTopic(null)
      await loadTopics()
      onTopicsChange()
      if (activeTopic === oldName) {
        onSelectTopic(renameValue.trim())
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to rename topic', 'error')
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await api.topics.delete(name)
      setDeletingTopic(null)
      setMenuOpen(null)
      await loadTopics()
      onTopicsChange()
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to delete topic', 'error')
    }
  }

  return (
    <aside className="border-r border-border bg-surface-1 flex flex-col shrink-0" style={style}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs text-text-dim font-semibold uppercase tracking-wider">Topics</span>
        <button
          onClick={() => { setCreating(true); setNewName('') }}
          className="text-text-dim hover:text-accent transition-colors text-lg leading-none"
          title="Create topic"
        >
          +
        </button>
      </div>

      {/* Topic list */}
      <div className="flex-1 overflow-y-auto py-1">
        {creating && (
          <div className="px-3 py-1">
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleCreate()
                if (e.key === 'Escape') setCreating(false)
              }}
              onBlur={() => { if (!newName.trim()) setCreating(false) }}
              placeholder="Topic name..."
              className="w-full bg-surface-2 border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
        )}

        {topics.map(t => (
          <div key={t.project_id}>
            <div
              className={`group flex items-center px-3 py-1.5 cursor-pointer text-sm transition-colors relative ${
                activeTopic === t.name
                  ? 'bg-accent-dim text-accent border-l-2 border-accent'
                  : 'text-text-secondary hover:bg-surface-2'
              }`}
              onClick={() => onSelectTopic(t.name)}
            >
              {renamingTopic === t.name ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleRename(t.name)
                    if (e.key === 'Escape') setRenamingTopic(null)
                  }}
                  onBlur={() => handleRename(t.name)}
                  onClick={e => e.stopPropagation()}
                  className="flex-1 bg-surface-2 border border-border rounded px-1 py-0.5 text-sm text-text-primary focus:outline-none focus:border-accent"
                />
              ) : (
                <>
                  <button
                    onClick={e => handleTogglePapers(t.name, e)}
                    className="mr-1 text-[10px] text-text-dim hover:text-text-secondary w-3 flex-shrink-0"
                  >
                    {expandedTopic === t.name ? '\u25BC' : '\u25B6'}
                  </button>
                  <span className="flex-1 truncate">{t.name}</span>
                  <span className="text-[10px] text-text-dim ml-1">{(() => {
                    const topicPaperList = topicPapers[t.name]
                    const selectedCount = topicPaperList
                      ? topicPaperList.filter(p => selectedPapers.has(p.arxiv_id)).length
                      : t.paper_count
                    const countDisplay = selectedCount < t.paper_count ? `${selectedCount}/${t.paper_count}` : `${t.paper_count}`
                    return `${countDisplay} \u00B7 ${t.size}`
                  })()}</span>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      setMenuOpen(menuOpen === t.name ? null : t.name)
                    }}
                    className="ml-1 opacity-0 group-hover:opacity-100 text-text-dim hover:text-text-secondary transition-opacity"
                  >
                    &hellip;
                  </button>
                </>
              )}

              {/* Context menu */}
              {menuOpen === t.name && (
                <div className="absolute right-2 top-full z-20 bg-surface-2 border border-border rounded shadow-lg text-xs">
                  <button
                    className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
                    onClick={e => {
                      e.stopPropagation()
                      setRenamingTopic(t.name)
                      setRenameValue(t.name)
                      setMenuOpen(null)
                    }}
                  >
                    Rename
                  </button>
                  <button
                    className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-red"
                    onClick={e => {
                      e.stopPropagation()
                      setDeletingTopic(t.name)
                      setMenuOpen(null)
                    }}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>

            {/* Collapsible paper list */}
            {expandedTopic === t.name && topicPapers[t.name] && (
              <div className="bg-surface-0/50">
                <div className="flex items-center gap-2 px-3 pl-7 py-1 text-[10px] text-text-dim">
                  <button
                    className="hover:text-accent"
                    onClick={() => {
                      const allIds = new Set(topicPapers[t.name].map(p => p.arxiv_id))
                      onSelectionChange(allIds)
                    }}
                  >All</button>
                  <span>/</span>
                  <button
                    className="hover:text-accent"
                    onClick={() => onSelectionChange(new Set())}
                  >None</button>
                </div>
                {topicPapers[t.name].map(p => (
                  <div
                    key={p.arxiv_id}
                    className={`flex items-center gap-1 px-3 pl-7 py-1 text-xs cursor-pointer ${
                      viewingPaperId === p.arxiv_id
                        ? 'bg-accent-dim text-accent'
                        : 'text-text-secondary hover:bg-surface-2'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedPapers.has(p.arxiv_id)}
                      onChange={(e) => {
                        e.stopPropagation()
                        const next = new Set(selectedPapers)
                        if (next.has(p.arxiv_id)) {
                          next.delete(p.arxiv_id)
                        } else {
                          next.add(p.arxiv_id)
                        }
                        onSelectionChange(next)
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="shrink-0 accent-accent"
                    />
                    <span
                      className="truncate cursor-pointer hover:text-accent"
                      onClick={(e) => { e.stopPropagation(); if (activeTopic !== t.name) onSelectTopic(t.name); onPaperClick(p) }}
                      title={`${p.title}\n${p.authors[0] ?? ''} \u00B7 ${p.date?.slice(0, 4) ?? ''}`}
                    >
                      {p.title}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {topics.length === 0 && !creating && (
          <div className="px-3 py-4 text-text-dim text-xs text-center">
            No topics yet. Click + to create one.
          </div>
        )}
      </div>

      {deletingTopic && (
        <ConfirmDialog
          title="Delete topic"
          message={`Delete "${deletingTopic}" and all its papers?`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => handleDelete(deletingTopic)}
          onCancel={() => setDeletingTopic(null)}
        />
      )}
    </aside>
  )
}
