import { useState, useCallback, useEffect, useRef } from 'react'

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
  const [helpOpen, setHelpOpen] = useState(false)

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

  const handleAddDocToTopic = useCallback(async (docId: string, topicName: string) => {
    await api.topicRepos.add(topicName, docId)
    setReposVersion(v => v + 1)
  }, [])

  const handleRemoveDocFromTopic = useCallback(async (docId: string, topicName: string) => {
    await api.topicRepos.remove(topicName, docId)
    setReposVersion(v => v + 1)
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

  return (
    <AppShell connected={connected}>
      <Header appName="Code Explorer" isDark={dark} onToggleTheme={toggleTheme} onHelpToggle={() => setHelpOpen(h => !h)}>
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
          addDocToTopic={handleAddDocToTopic}
          removeDocFromTopic={handleRemoveDocFromTopic}
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

      {helpOpen && (
        <HelpPanel
          onClose={() => setHelpOpen(false)}
          quickStart={[
            'Create a topic using the <strong>+</strong> button in the sidebar',
            'Click <strong>+ Repo</strong> and paste a GitHub URL',
            'Wait for the analysis to complete \u2014 you can check status in the sidebar',
            'Select repositories using the checkboxes, then ask questions in the chat',
            'Click <strong>View trace</strong> on any answer to see how the LLM explored the code',
          ]}
          faq={[
            { q: 'What does the analysis status mean?', a: '<strong>Current</strong> means the analysis reflects the latest commit. <strong>Stale</strong> means new commits exist \u2014 click \u201cCheck for Updates\u201d to refresh. <strong>Missing</strong> means no analysis yet \u2014 click \u201cGenerate Analysis.\u201d' },
            { q: 'How do I update a repository\u2019s analysis?', a: 'Open the repository detail view and click \u201cCheck for Updates.\u201d If new commits are found, the analysis is regenerated automatically.' },
            { q: 'Can a repository belong to multiple topics?', a: 'Yes. Use the context menu on a repository to add it to additional topics.' },
            { q: 'What does the context budget indicator mean?', a: 'It estimates how much of the model\u2019s context window is used by your repositories and conversation. Green (&lt;50%), amber (&lt;80%), red (\u226580%).' },
            { q: 'Why do queries take so long?', a: 'Shesha uses a recursive approach: the LLM writes code to explore your repositories, runs it, examines the output, and repeats. This takes multiple iterations.' },
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
