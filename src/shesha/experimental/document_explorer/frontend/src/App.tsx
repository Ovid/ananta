import { useState, useCallback, useEffect, useRef, type ReactNode } from 'react'

import {
  AppShell,
  Header,
  HelpPanel,
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
  const [helpOpen, setHelpOpen] = useState(false)
  const [allowBgKnowledge, setAllowBgKnowledge] = useState(false)

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

  const openDocDetail = useCallback((doc: DocumentInfo) => {
    setViewingDoc(doc)
    setViewingDocTopics([])
    api.documents.topics(doc.project_id).then(setViewingDocTopics)
  }, [])

  const handleViewDocument = useCallback((item: DocumentItem) => {
    const found = allDocsRef.current.find(d => d.project_id === item.id)
    if (found) openDocDetail(found)
  }, [openDocDetail])

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
            <button
              key={doc.project_id}
              onClick={() => openDocDetail(doc)}
              className="text-[10px] text-accent hover:underline bg-accent/5 rounded px-1.5 py-0.5"
              title={doc.filename}
            >
              {doc.filename}
            </button>
          ))}
        </div>
      </div>
    )
  }, [openDocDetail])

  return (
    <AppShell connected={connected}>
      <Header appName="Document Explorer" isDark={dark} onToggleTheme={toggleTheme} onHelpToggle={() => setHelpOpen(h => !h)}>
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
          deleteDocument={handleDeleteDocument}
          uncategorizedDocs={uncategorizedDocs}
          viewingDocumentId={viewingDoc?.project_id}
          style={{ width: sidebarWidth }}
          bottomControls={
            <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer select-none">
              <input
                type="checkbox"
                checked={allowBgKnowledge}
                onChange={e => setAllowBgKnowledge(e.target.checked)}
                className="accent-accent"
              />
              Allow background knowledge
            </label>
          }
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
            allowBackgroundKnowledge={allowBgKnowledge}
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
          downloadTrace={api.traces.download}
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

      {helpOpen && (
        <HelpPanel
          onClose={() => setHelpOpen(false)}
          quickStart={[
            <>Create a topic using the <strong>+</strong> button in the sidebar</>,
            <>Click <strong>Upload</strong> and drag-and-drop or select files</>,
            'Organize documents into topics using the context menu',
            'Select documents using the checkboxes, then ask questions in the chat',
            <>Click <strong>View trace</strong> on any answer to see how the LLM explored your documents</>,
          ]}
          faq={[
            { q: 'What file types can I upload?', a: 'PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), RTF, and any plain-text file \u2014 including Markdown, CSV, HTML, config files, and source code.' },
            { q: 'What are the \u201cSources\u201d shown below answers?', a: 'They list which documents the LLM consulted to produce the answer. Click a source tag to view that document\u2019s details.' },
            { q: 'Can a document belong to multiple topics?', a: 'Yes. Open the document detail view to see which topics it belongs to and add or remove it from others.' },
            { q: 'What does the context budget indicator mean?', a: <>It estimates how much of the model{'\u2019'}s context window is used by your documents and conversation. Green ({'<'}50%), amber ({'<'}80%), red ({'\u2265'}80%).</> },
            { q: 'Why do queries take so long?', a: 'Shesha uses a recursive approach: the LLM writes code to explore your documents, runs it, examines the output, and repeats. This takes multiple iterations.' },
            { q: 'What does the "More" button do?', a: 'It asks the AI to verify and expand its previous analysis. It checks for completeness, accuracy, and relevance, then presents an updated report with any changes highlighted. Requires at least one prior exchange.' },
            { q: 'What does "Allow background knowledge" do?', a: 'By default, answers are based strictly on your documents \u2014 this reduces hallucinations but may leave gaps. When enabled, the AI supplements document content with its general knowledge. Background knowledge sections are visually marked so you can tell what comes from your documents versus the AI.' },
          ]}
          shortcuts={[
            { label: 'Send message', key: 'Enter' },
            { label: 'New line in input', key: 'Shift+Enter' },
            { label: 'Cancel query', key: 'Escape' },
          ]}
        />
      )}

      <ToastContainer />
    </AppShell>
  )
}
