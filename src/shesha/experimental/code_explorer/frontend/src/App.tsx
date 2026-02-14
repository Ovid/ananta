import { useState, useCallback, useEffect, useRef, type MouseEvent } from 'react'

import {
  Header,
  TopicSidebar,
  ChatArea,
  StatusBar,
  TraceViewer,
  ToastContainer,
  showToast,
  useTheme,
  useWebSocket,
} from '@shesha/shared-ui'
import { api } from './api/client'
import AddRepoModal from './components/AddRepoModal'
import RepoDetail from './components/RepoDetail'
import type {
  RepoInfo,
  RepoAnalysis,
  ContextBudget,
  WSMessage,
  DocumentItem,
  Exchange,
  TopicInfo,
} from './types'

function repoToDocument(repo: RepoInfo): DocumentItem {
  return {
    id: repo.project_id,
    label: repo.project_id,
    sublabel: `${repo.file_count} files \u00B7 ${repo.analysis_status ?? 'no analysis'}`,
  }
}

export default function App() {
  const { dark, toggle: toggleTheme } = useTheme()
  const { connected, send, onMessage } = useWebSocket<WSMessage>()

  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [modelName, setModelName] = useState('\u2014')
  const [tokens, setTokens] = useState({ prompt: 0, completion: 0, total: 0 })
  const [budget, setBudget] = useState<ContextBudget | null>(null)
  const [phase, setPhase] = useState('Ready')
  const [selectedRepos, setSelectedRepos] = useState<Set<string>>(new Set())
  const [viewingRepo, setViewingRepo] = useState<RepoInfo | null>(null)
  const [viewingAnalysis, setViewingAnalysis] = useState<RepoAnalysis | null>(null)
  const [showAddRepo, setShowAddRepo] = useState(false)
  const [topicNames, setTopicNames] = useState<string[]>([])
  const [allRepos, setAllRepos] = useState<RepoInfo[]>([])
  const [uncategorizedRepos, setUncategorizedRepos] = useState<DocumentItem[]>([])
  const [sidebarWidth, setSidebarWidth] = useState(224)
  const [historyVersion, setHistoryVersion] = useState(0)
  const [reposVersion, setReposVersion] = useState(0)
  const [traceView, setTraceView] = useState<{ topic: string; traceId: string } | null>(null)

  const dragging = useRef(false)
  const allReposRef = useRef<RepoInfo[]>([])
  allReposRef.current = allRepos

  // Load model name on mount
  useEffect(() => {
    api.model.get().then(info => setModelName(info.model)).catch(() => {
      // Model API may not be available yet
    })
  }, [])

  // Load all repos (for uncategorized section and general repo data)
  useEffect(() => {
    api.repos.list().then(repos => {
      setAllRepos(repos)
      // All repos shown as uncategorized for now (topics are organizational)
      setUncategorizedRepos(repos.map(repoToDocument))
    }).catch(() => {
      // Repos API may not be available yet
    })
  }, [reposVersion])

  // Listen for WebSocket messages to update status bar
  useEffect(() => {
    return onMessage((msg) => {
      if (msg.type === 'status') {
        setPhase(msg.phase)
      } else if (msg.type === 'step') {
        setPhase(`${msg.step_type} (iter ${msg.iteration})`)
        if (msg.prompt_tokens !== undefined) {
          setTokens({
            prompt: msg.prompt_tokens,
            completion: msg.completion_tokens ?? 0,
            total: msg.prompt_tokens + (msg.completion_tokens ?? 0),
          })
        }
      } else if (msg.type === 'complete') {
        setPhase('Ready')
        setTokens(msg.tokens)
      } else if (msg.type === 'error') {
        setPhase('Error')
        showToast(msg.message ?? 'Unknown error', 'error')
      } else if (msg.type === 'cancelled') {
        setPhase('Ready')
      }
    })
  }, [onMessage])

  const handleTopicSelect = useCallback((name: string) => {
    setActiveTopic(name)
    setViewingRepo(null)
    setViewingAnalysis(null)
    setSelectedRepos(new Set())
    if (name) {
      api.contextBudget(name).then(setBudget).catch(() => {
        // Context budget may not be available for this topic
      })
    }
  }, [])

  const loadDocuments = useCallback(async (_topicName: string): Promise<DocumentItem[]> => {
    // Code explorer shows all repos under every topic (topics are organizational)
    const repos = await api.repos.list()
    return repos.map(repoToDocument)
  }, [])

  const handleLoadTopics = useCallback(async (): Promise<TopicInfo[]> => {
    const topics = await api.topics.list()
    setTopicNames(topics.map(t => t.name))
    return topics
  }, [])

  const handleDocsLoaded = useCallback((docs: DocumentItem[]) => {
    setSelectedRepos(new Set(docs.map(d => d.id)))
  }, [])

  const handleViewRepo = useCallback((doc: DocumentItem) => {
    const repo = allReposRef.current.find(r => r.project_id === doc.id)
    if (!repo) return
    setViewingRepo(repo)
    api.repos.getAnalysis(repo.project_id).then(analysis => {
      setViewingAnalysis(analysis)
    }).catch(() => {
      setViewingAnalysis(null)
    })
  }, [])

  const handleAddRepo = useCallback(async (url: string, topic?: string) => {
    try {
      await api.repos.add({ url, topic })
      setShowAddRepo(false)
      setReposVersion(v => v + 1)
      showToast('Repository added', 'success')
    } catch {
      showToast('Failed to add repository', 'error')
    }
  }, [])

  const handleAnalyze = useCallback(async (projectId: string) => {
    try {
      const analysis = await api.repos.analyze(projectId)
      setViewingAnalysis(analysis)
      showToast('Analysis complete', 'success')
    } catch {
      showToast('Failed to analyze repository', 'error')
    }
  }, [])

  const handleCheckUpdates = useCallback(async (projectId: string) => {
    try {
      const result = await api.repos.checkUpdates(projectId)
      if (result.status === 'updated') {
        setReposVersion(v => v + 1)
        showToast(`Updated: ${result.files_ingested} files ingested`, 'success')
      } else {
        showToast('Repository is up to date', 'success')
      }
    } catch {
      showToast('Failed to check for updates', 'error')
    }
  }, [])

  const handleRemoveRepo = useCallback(async (projectId: string) => {
    try {
      await api.repos.delete(projectId)
      setViewingRepo(null)
      setViewingAnalysis(null)
      setReposVersion(v => v + 1)
      setSelectedRepos(prev => {
        const next = new Set(prev)
        next.delete(projectId)
        return next
      })
      showToast('Repository removed', 'success')
    } catch {
      showToast('Failed to remove repository', 'error')
    }
  }, [])

  // Global history (ignores topic param since code explorer history is global)
  const loadHistory = useCallback(async (_topic: string): Promise<Exchange[]> => {
    const data = await api.history.get()
    return data.exchanges
  }, [])

  const handleClearHistory = useCallback(async () => {
    try {
      await api.history.clear()
      setHistoryVersion(v => v + 1)
      setTokens({ prompt: 0, completion: 0, total: 0 })
      showToast('Conversation cleared', 'success')
    } catch {
      showToast('Failed to clear conversation', 'error')
    }
  }, [])

  const handleViewTrace = useCallback((traceId: string) => {
    // Use activeTopic or a fallback for trace viewing
    setTraceView({ topic: activeTopic ?? '', traceId })
  }, [activeTopic])

  const handleExport = useCallback(async () => {
    try {
      const content = await api.export()
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'code-explorer-transcript.md'
      a.click()
      URL.revokeObjectURL(url)
      showToast('Transcript exported', 'success')
    } catch {
      showToast('Failed to export transcript', 'error')
    }
  }, [])

  const handleSidebarDrag = useCallback((e: MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX
    const startWidth = sidebarWidth
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!dragging.current) return
      const newWidth = Math.min(600, Math.max(160, startWidth + ev.clientX - startX))
      setSidebarWidth(newWidth)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarWidth])

  return (
    <div className="h-screen flex flex-col bg-surface-0 text-text-primary font-sans">
      <Header appName="Code Explorer" isDark={dark} onToggleTheme={toggleTheme}>
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

      {/* Connection loss banner */}
      {!connected && (
        <div className="bg-amber/10 border-b border-amber text-amber text-sm px-4 py-1.5 text-center">
          Connection lost. Reconnecting...
        </div>
      )}

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        <TopicSidebar
          activeTopic={activeTopic}
          onSelectTopic={handleTopicSelect}
          onTopicsChange={() => {}}
          refreshKey={reposVersion}
          selectedDocuments={selectedRepos}
          onSelectionChange={setSelectedRepos}
          onDocumentClick={handleViewRepo}
          onDocumentsLoaded={handleDocsLoaded}
          loadDocuments={loadDocuments}
          loadTopics={handleLoadTopics}
          createTopic={name => api.topics.create(name)}
          renameTopic={(o, n) => api.topics.rename(o, n)}
          deleteTopic={name => api.topics.delete(name)}
          addButton={
            <button
              onClick={() => setShowAddRepo(true)}
              title="Add repository"
              className="text-text-dim hover:text-accent transition-colors text-sm leading-none px-1"
            >
              + Repo
            </button>
          }
          uncategorizedDocs={uncategorizedRepos}
          viewingDocumentId={viewingRepo?.project_id}
          style={{ width: sidebarWidth }}
        />

        {/* Resize handle */}
        <div
          onMouseDown={handleSidebarDrag}
          className="w-1 cursor-col-resize hover:bg-accent/30 active:bg-accent/50 transition-colors shrink-0"
        />

        {/* Center column */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {viewingRepo && (
            <RepoDetail
              repo={viewingRepo}
              analysis={viewingAnalysis}
              onClose={() => { setViewingRepo(null); setViewingAnalysis(null) }}
              onAnalyze={handleAnalyze}
              onCheckUpdates={handleCheckUpdates}
              onRemove={handleRemoveRepo}
            />
          )}
          <div className={`flex-1 flex flex-col min-w-0 min-h-0 ${viewingRepo ? 'hidden' : ''}`}>
            <ChatArea
              topicName={activeTopic}
              connected={connected}
              wsSend={send}
              wsOnMessage={onMessage}
              onViewTrace={handleViewTrace}
              onClearHistory={handleClearHistory}
              historyVersion={historyVersion}
              selectedDocuments={selectedRepos}
              emptySelectionMessage="Select repositories in the sidebar first..."
              placeholder="Ask a question about the selected repositories..."
              loadHistory={loadHistory}
            />
          </div>
        </div>
      </div>

      <StatusBar
        topicName={activeTopic}
        modelName={modelName}
        tokens={tokens}
        budget={budget}
        phase={phase}
        onModelClick={() => {}}
      />

      {/* Overlays */}
      {traceView && (
        <TraceViewer
          topicName={traceView.topic}
          traceId={traceView.traceId}
          onClose={() => setTraceView(null)}
          fetchTrace={api.traces.get}
        />
      )}

      {showAddRepo && (
        <AddRepoModal
          topics={topicNames}
          onSubmit={handleAddRepo}
          onClose={() => setShowAddRepo(false)}
        />
      )}

      <ToastContainer />
    </div>
  )
}
