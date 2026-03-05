import { useState, useCallback, useEffect, useRef, type ReactNode } from 'react'

import {
  AppShell,
  Header,
  TopicSidebar,
  ChatArea,
  StatusBar,
  TraceViewer,
  ToastContainer,
  showToast,
  useAppState,
} from '@shesha/shared-ui'
import { api } from './api/client'
import UploadArea from './components/UploadArea'
import DocumentDetail from './components/DocumentDetail'
import { docToDocumentItem } from './components/DocumentItem'
import type {
  DocumentInfo,
  DocumentItem,
  Exchange,
  TopicInfo,
} from './types'

export default function App() {
  const {
    dark, toggleTheme, connected, send, onMessage,
    modelName, tokens, budget, phase, setPhase, documentBytes,
    sidebarWidth, handleSidebarDrag,
    activeTopic, handleTopicSelect: sharedTopicSelect,
    traceView, setTraceView, handleViewTrace,
    historyVersion, setHistoryVersion, setTokens,
  } = useAppState({
    onExtraMessage: (msg: Record<string, unknown>) => {
      if (msg.type === 'error') {
        setPhase('Error')
        showToast((msg.message as string) ?? 'Unknown error', 'error')
      }
    },
  })

  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set())
  const [viewingDoc, setViewingDoc] = useState<DocumentInfo | null>(null)
  const [viewingDocTopics, setViewingDocTopics] = useState<string[]>([])
  const [topicNames, setTopicNames] = useState<string[]>([])
  const [allDocs, setAllDocs] = useState<DocumentInfo[]>([])
  const [uncategorizedDocs, setUncategorizedDocs] = useState<DocumentItem[]>([])
  const [docsVersion, setDocsVersion] = useState(0)

  const allDocsRef = useRef<DocumentInfo[]>([])
  allDocsRef.current = allDocs

  useEffect(() => {
    api.documents.list().then(docs => {
      setAllDocs(docs)
    }).catch(() => {
      // Documents API may not be available yet
    })
    api.documents.listUncategorized().then(docs => {
      setUncategorizedDocs(docs.map(docToDocumentItem))
    }).catch(() => {
      // Uncategorized API may not be available yet
    })
  }, [docsVersion])

  const handleTopicSelect = useCallback((name: string) => {
    if (name !== activeTopic) {
      setSelectedDocs(new Set())
    }
    sharedTopicSelect(name)
    setViewingDoc(null)
  }, [activeTopic, sharedTopicSelect])

  const loadDocuments = useCallback(async (topicName: string): Promise<DocumentItem[]> => {
    const docs = await api.documents.listForTopic(topicName)
    return docs.map(docToDocumentItem)
  }, [])

  const handleLoadTopics = useCallback(async (): Promise<TopicInfo[]> => {
    const topics = await api.topics.list()
    setTopicNames(topics.map(t => t.name))
    return topics
  }, [])

  const handleDocsLoaded = useCallback((docs: DocumentItem[]) => {
    setSelectedDocs(new Set(docs.map(d => d.id)))
  }, [])

  const topicNamesRef = useRef<string[]>([])
  topicNamesRef.current = topicNames

  const handleViewDocument = useCallback((doc: DocumentItem) => {
    const found = allDocsRef.current.find(d => d.project_id === doc.id)
    if (!found) return
    setViewingDoc(found)
    // Find which topics contain this document
    setViewingDocTopics([])
    Promise.all(
      topicNamesRef.current.map(async t => {
        try {
          const topicDocs = await api.documents.listForTopic(t)
          if (topicDocs.some(d => d.project_id === found.project_id)) {
            return t
          }
        } catch {
          // Topic may not exist
        }
        return null
      })
    ).then(results => {
      setViewingDocTopics(results.filter((t): t is string => t !== null))
    })
  }, [])

  const handleUpload = useCallback(async (files: File[]) => {
    try {
      await api.documents.upload(files, activeTopic || undefined)
      setDocsVersion(v => v + 1)
      showToast(`${files.length} file${files.length > 1 ? 's' : ''} uploaded`, 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to upload files'
      showToast(msg, 'error')
    }
  }, [activeTopic])

  const handleDeleteDocument = useCallback(async (projectId: string) => {
    try {
      await api.documents.delete(projectId)
      setViewingDoc(null)
      setDocsVersion(v => v + 1)
      setSelectedDocs(prev => {
        const next = new Set(prev)
        next.delete(projectId)
        return next
      })
      showToast('Document deleted', 'success')
    } catch {
      showToast('Failed to delete document', 'error')
    }
  }, [])

  const handleAddDocToTopic = useCallback(async (docId: string, topicName: string) => {
    await api.topicDocs.add(topicName, docId)
    setDocsVersion(v => v + 1)
  }, [])

  const handleRemoveDocFromTopic = useCallback(async (docId: string, topicName: string) => {
    await api.topicDocs.remove(topicName, docId)
    setDocsVersion(v => v + 1)
  }, [])

  const loadHistory = useCallback(async (topic: string): Promise<Exchange[]> => {
    const data = await api.history.get(topic)
    return data.exchanges
  }, [])

  const handleClearHistory = useCallback(async () => {
    if (!activeTopic) return
    try {
      await api.history.clear(activeTopic)
      setHistoryVersion(v => v + 1)
      setTokens({ prompt: 0, completion: 0, total: 0 })
      showToast('Conversation cleared', 'success')
    } catch {
      showToast('Failed to clear conversation', 'error')
    }
  }, [activeTopic, setHistoryVersion, setTokens])

  const handleExport = useCallback(async () => {
    if (!activeTopic) return
    try {
      const content = await api.export(activeTopic)
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${activeTopic}-transcript.md`
      a.click()
      URL.revokeObjectURL(url)
      showToast('Transcript exported', 'success')
    } catch {
      showToast('Failed to export transcript', 'error')
    }
  }, [activeTopic])

  const renderAnswerFooter = useCallback((exchange: Exchange): ReactNode => {
    const ids = exchange.document_ids
    if (!ids || ids.length === 0) return undefined

    const consulted = ids
      .map(pid => allDocsRef.current.find(d => d.project_id === pid))
      .filter((d): d is DocumentInfo => d != null)

    if (consulted.length === 0) return undefined

    return (
      <div className="mt-2 pt-2 border-t border-border">
        <div className="text-[10px] text-text-dim mb-1">Sources:</div>
        <div className="flex flex-wrap gap-1">
          {consulted.map(doc => (
            <span
              key={doc.project_id}
              className="text-[10px] text-accent bg-accent/5 rounded px-1.5 py-0.5"
              title={doc.filename}
            >
              {doc.filename}
            </span>
          ))}
        </div>
      </div>
    )
  }, [])

  return (
    <AppShell connected={connected}>
      <Header appName="Document Explorer" isDark={dark} onToggleTheme={toggleTheme}>
        <button
          onClick={handleExport}
          className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          aria-label="Export transcript"
          data-tooltip="Export transcript"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </button>
      </Header>

      <div className="flex-1 flex overflow-hidden">
        <TopicSidebar
          activeTopic={activeTopic}
          onSelectTopic={handleTopicSelect}
          onTopicsChange={() => {}}
          refreshKey={docsVersion}
          selectedDocuments={selectedDocs}
          onSelectionChange={setSelectedDocs}
          onDocumentClick={handleViewDocument}
          onDocumentsLoaded={handleDocsLoaded}
          loadDocuments={loadDocuments}
          loadTopics={handleLoadTopics}
          createTopic={async name => { await api.topics.create(name) }}
          renameTopic={async (o, n) => { await api.topics.rename(o, n) }}
          deleteTopic={async name => { await api.topics.delete(name) }}
          addButton={<UploadArea onUpload={handleUpload} />}
          addDocToTopic={handleAddDocToTopic}
          removeDocFromTopic={handleRemoveDocFromTopic}
          uncategorizedDocs={uncategorizedDocs}
          viewingDocumentId={viewingDoc?.project_id}
          style={{ width: sidebarWidth }}
        />

        <div
          onMouseDown={handleSidebarDrag}
          className="w-1 cursor-col-resize hover:bg-accent/30 active:bg-accent/50 transition-colors shrink-0"
        />

        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <ChatArea
            topicName={activeTopic}
            connected={connected}
            wsSend={send}
            wsOnMessage={onMessage}
            onViewTrace={handleViewTrace}
            onClearHistory={handleClearHistory}
            historyVersion={historyVersion}
            selectedDocuments={selectedDocs}
            emptySelectionMessage="Upload documents and select them in the sidebar first..."
            placeholder="Ask a question about the selected documents..."
            loadHistory={loadHistory}
            renderAnswerFooter={renderAnswerFooter}
          />
        </div>
      </div>

      <StatusBar
        topicName={activeTopic}
        modelName={modelName}
        tokens={tokens}
        budget={budget}
        phase={phase}
        onModelClick={() => {}}
        documentBytes={documentBytes}
      />

      {traceView && (
        <TraceViewer
          topicName={traceView.topic}
          traceId={traceView.traceId}
          onClose={() => setTraceView(null)}
          fetchTrace={api.traces.get}
        />
      )}

      {viewingDoc && (
        <DocumentDetail
          doc={viewingDoc}
          topics={topicNames}
          docTopics={viewingDocTopics}
          onClose={() => setViewingDoc(null)}
          onDelete={handleDeleteDocument}
          onAddToTopic={handleAddDocToTopic}
          onRemoveFromTopic={handleRemoveDocFromTopic}
        />
      )}

      <ToastContainer />
    </AppShell>
  )
}
