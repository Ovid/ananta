import { useState, useEffect, type CSSProperties, type MouseEvent, type ReactNode } from 'react'

import { showToast } from './Toast'
import ConfirmDialog from './ConfirmDialog'
import type { TopicInfo, DocumentItem } from '../types'

export interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
  refreshKey: number
  selectedDocuments: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  onDocumentClick: (doc: DocumentItem) => void
  onDocumentsLoaded?: (docs: DocumentItem[]) => void
  loadDocuments: (topicName: string) => Promise<DocumentItem[]>
  loadTopics: () => Promise<TopicInfo[]>
  createTopic: (name: string) => Promise<void>
  renameTopic: (oldName: string, newName: string) => Promise<void>
  deleteTopic: (name: string) => Promise<void>
  addButton?: ReactNode
  uncategorizedDocs?: DocumentItem[]
  viewingDocumentId?: string | null
  style?: CSSProperties
}

export default function TopicSidebar({
  activeTopic,
  onSelectTopic,
  onTopicsChange,
  refreshKey,
  selectedDocuments,
  onSelectionChange,
  onDocumentClick,
  onDocumentsLoaded,
  loadDocuments,
  loadTopics,
  createTopic,
  renameTopic,
  deleteTopic,
  addButton,
  uncategorizedDocs,
  viewingDocumentId,
  style,
}: TopicSidebarProps) {
  const [topics, setTopics] = useState<TopicInfo[]>([])
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renamingTopic, setRenamingTopic] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null)
  const [topicDocs, setTopicDocs] = useState<Record<string, DocumentItem[]>>({})
  const [deletingTopic, setDeletingTopic] = useState<string | null>(null)

  const refreshTopics = async () => {
    try {
      const data = await loadTopics()
      setTopics(data)
    } catch {
      showToast('Failed to load topics', 'error')
    }
  }

  useEffect(() => { refreshTopics() }, [refreshKey])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setTopicDocs({}) }, [refreshKey])

  // Auto-expand and load documents when active topic changes
  useEffect(() => {
    if (!activeTopic) return
    setExpandedTopic(activeTopic)
    if (!topicDocs[activeTopic]) {
      loadDocuments(activeTopic).then(docs => {
        setTopicDocs(prev => ({ ...prev, [activeTopic]: docs }))
        onDocumentsLoaded?.(docs)
      }).catch(() => {
        // Document loading failed; topic may have no documents
      })
    } else {
      onDocumentsLoaded?.(topicDocs[activeTopic])
    }
  }, [activeTopic])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggleDocs = async (topicName: string, e: MouseEvent) => {
    e.stopPropagation()
    if (expandedTopic === topicName) {
      setExpandedTopic(null)
      return
    }
    setExpandedTopic(topicName)
    if (!topicDocs[topicName]) {
      try {
        const docs = await loadDocuments(topicName)
        setTopicDocs(prev => ({ ...prev, [topicName]: docs }))
        onDocumentsLoaded?.(docs)
      } catch {
        showToast('Failed to load documents', 'error')
      }
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await createTopic(newName.trim())
      setCreating(false)
      setNewName('')
      await refreshTopics()
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
      await renameTopic(oldName, renameValue.trim())
      setRenamingTopic(null)
      await refreshTopics()
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
      await deleteTopic(name)
      setDeletingTopic(null)
      setMenuOpen(null)
      await refreshTopics()
      onTopicsChange()
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to delete topic', 'error')
    }
  }

  const renderDocList = (docs: DocumentItem[], topicName: string) => (
    <div className="bg-surface-0/50">
      <div className="flex items-center gap-2 px-3 pl-7 py-1 text-[10px] text-text-dim">
        <button
          className="hover:text-accent"
          onClick={() => {
            // "All" — add this topic's docs to selection, preserving other selections
            const next = new Set(selectedDocuments)
            for (const doc of docs) {
              next.add(doc.id)
            }
            onSelectionChange(next)
          }}
        >All</button>
        <span>/</span>
        <button
          className="hover:text-accent"
          onClick={() => {
            // "None" — remove only this topic's docs from selection
            const topicIds = new Set(docs.map(d => d.id))
            const next = new Set(selectedDocuments)
            for (const id of topicIds) {
              next.delete(id)
            }
            onSelectionChange(next)
          }}
        >None</button>
      </div>
      {docs.map(doc => (
        <div
          key={doc.id}
          className={`flex items-center gap-1 px-3 pl-7 py-1 text-xs cursor-pointer ${
            viewingDocumentId === doc.id
              ? 'bg-accent-dim text-accent'
              : 'text-text-secondary hover:bg-surface-2'
          }`}
        >
          <input
            type="checkbox"
            checked={selectedDocuments.has(doc.id)}
            onChange={(e) => {
              e.stopPropagation()
              const next = new Set(selectedDocuments)
              if (next.has(doc.id)) {
                next.delete(doc.id)
              } else {
                next.add(doc.id)
              }
              onSelectionChange(next)
            }}
            onClick={(e) => e.stopPropagation()}
            className="shrink-0 accent-accent"
          />
          <span
            className="truncate cursor-pointer hover:text-accent"
            onClick={(e) => {
              e.stopPropagation()
              if (activeTopic !== topicName) onSelectTopic(topicName)
              onDocumentClick(doc)
            }}
            title={doc.sublabel ? `${doc.label}\n${doc.sublabel}` : doc.label}
          >
            {doc.label}
          </span>
        </div>
      ))}
    </div>
  )

  return (
    <aside className="border-r border-border bg-surface-1 flex flex-col shrink-0" style={style}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-1">
          <span className="text-xs text-text-dim font-semibold uppercase tracking-wider">Topics</span>
          <button
            onClick={() => { setCreating(true); setNewName('') }}
            className="text-text-dim hover:text-accent transition-colors text-lg leading-none"
            title="Create topic"
          >
            +
          </button>
        </div>
        {addButton}
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
                    onClick={e => handleToggleDocs(t.name, e)}
                    className="mr-1 text-[10px] text-text-dim hover:text-text-secondary w-3 flex-shrink-0"
                  >
                    {expandedTopic === t.name ? '\u25BC' : '\u25B6'}
                  </button>
                  <span className="flex-1 truncate">{t.name}</span>
                  <span className="text-[10px] text-text-dim ml-1">{(() => {
                    const topicDocList = topicDocs[t.name]
                    const selectedCount = topicDocList
                      ? topicDocList.filter(d => selectedDocuments.has(d.id)).length
                      : t.document_count
                    const countDisplay = selectedCount < t.document_count ? `${selectedCount}/${t.document_count}` : `${t.document_count}`
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

            {/* Collapsible document list */}
            {expandedTopic === t.name && topicDocs[t.name] && renderDocList(topicDocs[t.name], t.name)}
          </div>
        ))}

        {topics.length === 0 && !creating && (
          <div className="px-3 py-4 text-text-dim text-xs text-center">
            No topics yet. Click + to create one.
          </div>
        )}

        {/* Uncategorized docs section */}
        {uncategorizedDocs && uncategorizedDocs.length > 0 && (
          <div className="border-t border-border mt-1 pt-1">
            <div className="px-3 py-1.5 text-sm text-text-dim font-medium">Uncategorized</div>
            {uncategorizedDocs.map(doc => (
              <div
                key={doc.id}
                className={`flex items-center gap-1 px-3 pl-7 py-1 text-xs cursor-pointer ${
                  viewingDocumentId === doc.id
                    ? 'bg-accent-dim text-accent'
                    : 'text-text-secondary hover:bg-surface-2'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedDocuments.has(doc.id)}
                  onChange={(e) => {
                    e.stopPropagation()
                    const next = new Set(selectedDocuments)
                    if (next.has(doc.id)) {
                      next.delete(doc.id)
                    } else {
                      next.add(doc.id)
                    }
                    onSelectionChange(next)
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 accent-accent"
                />
                <span
                  className="truncate cursor-pointer hover:text-accent"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDocumentClick(doc)
                  }}
                  title={doc.sublabel ? `${doc.label}\n${doc.sublabel}` : doc.label}
                >
                  {doc.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {deletingTopic && (
        <ConfirmDialog
          title="Delete topic"
          message={`Delete "${deletingTopic}" and all its documents?`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => handleDelete(deletingTopic)}
          onCancel={() => setDeletingTopic(null)}
        />
      )}
    </aside>
  )
}
