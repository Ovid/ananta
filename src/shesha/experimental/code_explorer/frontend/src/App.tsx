import { useState, useCallback, useEffect, useRef } from 'react'

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
import AddRepoModal from './components/AddRepoModal'
import RepoDetail from './components/RepoDetail'
import type {
  RepoInfo,
  RepoAnalysis,
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
  const {
    dark, toggleTheme, connected, send, onMessage,
    modelName, tokens, budget, phase, setPhase, documentBytes,
    sidebarWidth, handleSidebarDrag,
    activeTopic, handleTopicSelect: sharedTopicSelect,
    traceView, setTraceView, handleViewTrace,
    historyVersion, setHistoryVersion, setTokens,
  } = useAppState({
    onExtraMessage: (msg: any) => {
      if (msg.type === 'error') {
        setPhase('Error')
        showToast(msg.message ?? 'Unknown error', 'error')
      }
    },
  })

  const [selectedRepos, setSelectedRepos] = useState<Set<string>>(new Set())
  const [viewingRepo, setViewingRepo] = useState<RepoInfo | null>(null)
  const [viewingAnalysis, setViewingAnalysis] = useState<RepoAnalysis | null>(null)
  const [showAddRepo, setShowAddRepo] = useState(false)
  const [topicNames, setTopicNames] = useState<string[]>([])
  const [allRepos, setAllRepos] = useState<RepoInfo[]>([])
  const [uncategorizedRepos, setUncategorizedRepos] = useState<DocumentItem[]>([])
  const [reposVersion, setReposVersion] = useState(0)

  const allReposRef = useRef<RepoInfo[]>([])
  allReposRef.current = allRepos

  // Load all repos (for general repo data) and uncategorized repos separately
  useEffect(() => {
    api.repos.list().then(repos => {
      setAllRepos(repos)
    }).catch(() => {
      // Repos API may not be available yet
    })
    api.repos.listUncategorized().then(repos => {
      setUncategorizedRepos(repos.map(repoToDocument))
    }).catch(() => {
      // Uncategorized API may not be available yet
    })
  }, [reposVersion])

  const handleTopicSelect = useCallback((name: string) => {
    if (name !== activeTopic) {
      setSelectedRepos(new Set())
    }
    sharedTopicSelect(name)
    setViewingRepo(null)
    setViewingAnalysis(null)
  }, [activeTopic, sharedTopicSelect])

  const loadDocuments = useCallback(async (topicName: string): Promise<DocumentItem[]> => {
    const repos = await api.repos.listForTopic(topicName)
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
      if (result.status === 'updates_available') {
        const applied = await api.repos.applyUpdates(projectId)
        setReposVersion(v => v + 1)
        showToast(`Updated: ${applied.files_ingested} files ingested`, 'success')
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
  }, [setHistoryVersion, setTokens])

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

  return (
    <AppShell connected={connected}>
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
          createTopic={async name => { await api.topics.create(name) }}
          renameTopic={async (o, n) => { await api.topics.rename(o, n) }}
          deleteTopic={async name => { await api.topics.delete(name) }}
          addButton={
            <button
              onClick={() => setShowAddRepo(true)}
              title="Add repository"
              className="text-[10px] text-text-dim hover:text-accent border border-border hover:border-accent/50 rounded px-1.5 py-0.5 transition-colors"
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
        documentBytes={documentBytes}
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
    </AppShell>
  )
}
