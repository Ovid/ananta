import { useState, useEffect, useRef, useCallback, type CSSProperties, type MouseEvent, type DragEvent, type ReactNode } from 'react'

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
  addDocToTopic?: (docId: string, topicName: string) => Promise<void>
  removeDocFromTopic?: (docId: string, topicName: string) => Promise<void>
  deleteDocument?: (docId: string) => Promise<void>
  renameDocument?: (docId: string, newLabel: string) => Promise<void>
  reorderItems?: (topicName: string, itemIds: string[]) => Promise<void>
  addButton?: ReactNode
  bottomControls?: ReactNode
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
  addDocToTopic,
  removeDocFromTopic,
  deleteDocument,
  renameDocument,
  reorderItems,
  addButton,
  bottomControls,
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
  const [docMenuOpen, setDocMenuOpen] = useState<string | null>(null)
  const [docSubmenuOpen, setDocSubmenuOpen] = useState(false)
  const [deletingDoc, setDeletingDoc] = useState<DocumentItem | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [renamingDoc, setRenamingDoc] = useState<string | null>(null)
  const [renameDocValue, setRenameDocValue] = useState('')
  const sidebarRef = useRef<HTMLElement>(null)

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: globalThis.MouseEvent) => {
      if (sidebarRef.current && !sidebarRef.current.contains(e.target as Node)) {
        setMenuOpen(null)
        setDocMenuOpen(null)
        setDocSubmenuOpen(false)
      }
      // Also close if clicking inside sidebar but not on a menu or its trigger
      const target = e.target as HTMLElement
      if (!target.closest('.absolute') && !target.closest('[title="Document actions"]') && !target.closest('button[class*="opacity-0"]')) {
        setMenuOpen(null)
        setDocMenuOpen(null)
        setDocSubmenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleDocDragStart = useCallback((e: DragEvent<HTMLDivElement>, docId: string, topicName: string | null) => {
    e.dataTransfer.setData('application/x-doc-id', docId)
    e.dataTransfer.setData('application/x-source-topic', topicName ?? '')
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleTopicDragOver = useCallback((e: DragEvent<HTMLDivElement>, topicName: string) => {
    if (!addDocToTopic) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDropTarget(topicName)
  }, [addDocToTopic])

  const handleTopicDragLeave = useCallback(() => {
    setDropTarget(null)
  }, [])

  const handleTopicDrop = useCallback(async (e: DragEvent<HTMLDivElement>, topicName: string) => {
    e.preventDefault()
    setDropTarget(null)
    const docId = e.dataTransfer.getData('application/x-doc-id')
    if (!docId || !addDocToTopic) return
    try {
      await addDocToTopic(docId, topicName)
      showToast(`Added to ${topicName}`, 'success')
    } catch {
      showToast(`Failed to add to ${topicName}`, 'error')
    }
  }, [addDocToTopic])

  const handleDocDrop = useCallback(async (e: DragEvent<HTMLDivElement>, targetDocId: string, topicName: string) => {
    e.preventDefault()
    e.stopPropagation()
    const draggedId = e.dataTransfer.getData('application/x-doc-id')
    const sourceTopic = e.dataTransfer.getData('application/x-source-topic')
    if (!draggedId || draggedId === targetDocId) return
    // Only reorder within the same topic
    if (sourceTopic !== topicName || !reorderItems) return
    const docs = topicDocs[topicName]
    if (!docs) return
    const ids = docs.map(d => d.id)
    const fromIdx = ids.indexOf(draggedId)
    const toIdx = ids.indexOf(targetDocId)
    if (fromIdx === -1 || toIdx === -1) return
    // Move draggedId to the position of targetDocId
    ids.splice(fromIdx, 1)
    ids.splice(toIdx, 0, draggedId)
    try {
      await reorderItems(topicName, ids)
      // Update local state immediately for responsiveness
      const reordered = ids.map(id => docs.find(d => d.id === id)!).filter(Boolean)
      setTopicDocs(prev => ({ ...prev, [topicName]: reordered }))
    } catch {
      showToast('Failed to reorder', 'error')
    }
  }, [reorderItems, topicDocs])

  const handleDocRename = useCallback(async (docId: string) => {
    if (!renameDocValue.trim() || !renameDocument) {
      setRenamingDoc(null)
      return
    }
    try {
      await renameDocument(docId, renameDocValue.trim())
      setRenamingDoc(null)
      setTopicDocs({})
      await refreshTopics()
      onTopicsChange()
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to rename document', 'error')
    }
  }, [renameDocValue, renameDocument, onTopicsChange]) // eslint-disable-line react-hooks/exhaustive-deps

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

  // Auto-expand and load documents when active topic or data changes
  useEffect(() => {
    if (!activeTopic) return
    setExpandedTopic(activeTopic)
    loadDocuments(activeTopic).then(docs => {
      setTopicDocs(prev => ({ ...prev, [activeTopic]: docs }))
      onDocumentsLoaded?.(docs)
    }).catch(() => {
      // Document loading failed; topic may have no documents
    })
  }, [activeTopic, refreshKey])  // eslint-disable-line react-hooks/exhaustive-deps

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

  const renderDocMenu = (doc: DocumentItem, topicName: string | null) => (
    <>
      {(addDocToTopic || deleteDocument || removeDocFromTopic || renameDocument) && (
        <button
          title="Document actions"
          onClick={e => {
            e.stopPropagation()
            setDocMenuOpen(docMenuOpen === doc.id ? null : doc.id)
            setDocSubmenuOpen(false)
          }}
          className="ml-auto opacity-0 group-hover:opacity-100 text-text-dim hover:text-text-secondary transition-opacity text-xs px-1"
        >
          &hellip;
        </button>
      )}
      {docMenuOpen === doc.id && (
        <div className="absolute right-0 top-full z-20 bg-surface-2 border border-border rounded shadow-lg text-xs min-w-[140px]">
          <button
            className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
            onClick={e => {
              e.stopPropagation()
              onDocumentClick(doc)
              setDocMenuOpen(null)
            }}
          >
            View
          </button>
          {renameDocument && (
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
              onClick={e => {
                e.stopPropagation()
                setRenamingDoc(doc.id)
                setRenameDocValue(doc.label)
                setDocMenuOpen(null)
              }}
            >
              Rename
            </button>
          )}
          {addDocToTopic && (() => {
            const eligible = topics.filter(t => {
              const loaded = topicDocs[t.name]
              return !loaded || !loaded.some(d => d.id === doc.id || d.label === doc.label)
            })
            if (eligible.length === 0) return null
            return (
              <>
                <button
                  className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
                  onClick={e => {
                    e.stopPropagation()
                    setDocSubmenuOpen(!docSubmenuOpen)
                  }}
                >
                  Add to&hellip;
                </button>
                {docSubmenuOpen && eligible.map(t => (
                  <button
                    key={t.name}
                    className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary pl-6"
                    onClick={async e => {
                      e.stopPropagation()
                      try {
                        await addDocToTopic(doc.id, t.name)
                        showToast(`Added to ${t.name}`, 'success')
                      } catch {
                        showToast(`Failed to add to ${t.name}`, 'error')
                      }
                      setDocMenuOpen(null)
                    }}
                  >
                    {t.name}
                  </button>
                ))}
              </>
            )
          })()}
          {removeDocFromTopic && topicName && (
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-red"
              onClick={async e => {
                e.stopPropagation()
                try {
                  await removeDocFromTopic(doc.id, topicName)
                  showToast(`Removed from ${topicName}`, 'success')
                } catch {
                  showToast(`Failed to remove from ${topicName}`, 'error')
                }
                setDocMenuOpen(null)
              }}
            >
              Remove from {topicName}
            </button>
          )}
          {deleteDocument && (
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-red"
              onClick={e => {
                e.stopPropagation()
                setDeletingDoc(doc)
                setDocMenuOpen(null)
              }}
            >
              Delete
            </button>
          )}
        </div>
      )}
    </>
  )

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
          draggable={!!addDocToTopic}
          onDragStart={e => handleDocDragStart(e, doc.id, topicName)}
          onDragOver={reorderItems ? (e => { e.preventDefault(); e.stopPropagation() }) : undefined}
          onDrop={reorderItems ? (e => handleDocDrop(e, doc.id, topicName)) : undefined}
          className={`group relative flex items-center gap-1 px-3 pl-7 py-1 text-xs cursor-pointer ${
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
          {renamingDoc === doc.id ? (
            <input
              autoFocus
              value={renameDocValue}
              onChange={e => setRenameDocValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleDocRename(doc.id)
                if (e.key === 'Escape') setRenamingDoc(null)
              }}
              onBlur={() => handleDocRename(doc.id)}
              onClick={e => e.stopPropagation()}
              className="flex-1 bg-surface-2 border border-border rounded px-1 py-0.5 text-xs text-text-primary focus:outline-none focus:border-accent"
            />
          ) : (
            <div
              className="min-w-0 cursor-pointer flex flex-col"
              onClick={(e) => {
                e.stopPropagation()
                if (activeTopic !== topicName) onSelectTopic(topicName)
                onDocumentClick(doc)
              }}
              title={doc.sublabel ? `${doc.label}\n${doc.sublabel}` : doc.label}
            >
              <span className="truncate hover:text-accent">{doc.label}</span>
              {doc.subtitle && (
                <span data-testid="doc-subtitle" className="truncate text-xs text-text-dim">
                  {doc.subtitle}
                </span>
              )}
            </div>
          )}
          {renderDocMenu(doc, topicName)}
        </div>
      ))}
    </div>
  )

  return (
    <aside ref={sidebarRef} className="border-r border-border bg-surface-1 flex flex-col shrink-0" style={style}>
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
              }${dropTarget === t.name ? ' drop-target ring-2 ring-accent ring-inset' : ''}`}
              onClick={() => onSelectTopic(t.name)}
              onDragOver={e => handleTopicDragOver(e, t.name)}
              onDragLeave={handleTopicDragLeave}
              onDrop={e => handleTopicDrop(e, t.name)}
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
                draggable={!!addDocToTopic}
                onDragStart={e => handleDocDragStart(e, doc.id, null)}
                className={`group relative flex items-center gap-1 px-3 pl-7 py-1 text-xs cursor-pointer ${
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
                {renamingDoc === doc.id ? (
                  <input
                    autoFocus
                    value={renameDocValue}
                    onChange={e => setRenameDocValue(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleDocRename(doc.id)
                      if (e.key === 'Escape') setRenamingDoc(null)
                    }}
                    onBlur={() => handleDocRename(doc.id)}
                    onClick={e => e.stopPropagation()}
                    className="flex-1 bg-surface-2 border border-border rounded px-1 py-0.5 text-xs text-text-primary focus:outline-none focus:border-accent"
                  />
                ) : (
                  <div
                    className="min-w-0 cursor-pointer flex flex-col"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDocumentClick(doc)
                    }}
                    title={doc.sublabel ? `${doc.label}\n${doc.sublabel}` : doc.label}
                  >
                    <span className="truncate hover:text-accent">{doc.label}</span>
                    {doc.subtitle && (
                      <span data-testid="doc-subtitle" className="truncate text-xs text-text-dim">
                        {doc.subtitle}
                      </span>
                    )}
                  </div>
                )}
                {renderDocMenu(doc, null)}
              </div>
            ))}
          </div>
        )}
      </div>

      {bottomControls && (
        <div className="border-t border-border px-3 py-2">
          {bottomControls}
        </div>
      )}

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

      {deletingDoc && deleteDocument && (
        <ConfirmDialog
          title="Delete document"
          message={`Delete "${deletingDoc.label}"?`}
          confirmLabel="Delete"
          destructive
          onConfirm={async () => {
            try {
              await deleteDocument(deletingDoc.id)
              setTopicDocs({})
              await refreshTopics()
              onTopicsChange()
            } catch {
              showToast('Failed to delete document', 'error')
            }
            setDeletingDoc(null)
          }}
          onCancel={() => setDeletingDoc(null)}
        />
      )}
    </aside>
  )
}
