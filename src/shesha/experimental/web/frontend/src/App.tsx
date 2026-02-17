import { useState, useCallback, useEffect, useRef } from 'react'
import Header from './components/Header'
import TopicSidebar from './components/TopicSidebar'
import ChatArea from './components/ChatArea'
import SearchPanel from './components/SearchPanel'
import HelpPanel from './components/HelpPanel'
import DownloadProgress from './components/DownloadProgress'
import CitationReport from './components/CitationReport'
import EmailModal, { getStoredEmail, hasEmailDecision } from './components/EmailModal'
import PaperDetail from './components/PaperDetail'
import { AppShell, useAppState, StatusBar, ToastContainer, showToast, TraceViewer } from '@shesha/shared-ui'
import { api } from './api/client'
import type { PaperInfo, PaperReport } from './types'

export default function App() {
  // Citation check state — ref tracks state for use in onExtraMessage closure
  const [citationChecking, setCitationChecking] = useState(false)
  const citationCheckingRef = useRef(false)
  useEffect(() => { citationCheckingRef.current = citationChecking }, [citationChecking])
  const [citationProgress, setCitationProgress] = useState<{ current: number; total: number; phase?: string } | null>(null)
  const [citationReport, setCitationReport] = useState<PaperReport[] | null>(null)
  const [citationError, setCitationError] = useState<string | null>(null)

  // activeTopicRef for use in onComplete closure (avoids stale closure over activeTopic)
  const activeTopicRef = useRef<string | null>(null)

  const {
    dark, toggleTheme,
    connected, send, onMessage,
    modelName, tokens, budget, setBudget, phase, setPhase, documentBytes,
    sidebarWidth, handleSidebarDrag,
    activeTopic, handleTopicSelect: baseHandleTopicSelect,
    traceView, setTraceView, handleViewTrace,
    historyVersion, setHistoryVersion,
    setTokens,
  } = useAppState({
    onComplete: () => {
      if (activeTopicRef.current) {
        api.contextBudget(activeTopicRef.current).then(setBudget).catch(() => {
          // Context budget may not be available
        })
      }
    },
    onExtraMessage: (msg: any) => {
      if (msg.type === 'error') {
        const errorMsg = msg.message ?? 'Unknown error'
        if (citationCheckingRef.current) {
          setCitationChecking(false)
          setCitationError(errorMsg)
        } else {
          setPhase('Error')
          showToast(errorMsg, 'error')
        }
      } else if (msg.type === 'citation_progress') {
        setCitationProgress({ current: msg.current, total: msg.total, phase: msg.phase })
      } else if (msg.type === 'citation_report') {
        setCitationChecking(false)
        setCitationReport(msg.papers)
      }
    },
  })

  // Keep activeTopicRef in sync with activeTopic from useAppState
  activeTopicRef.current = activeTopic

  const [selectedPapers, setSelectedPapers] = useState<Set<string>>(new Set())
  const [viewingPaper, setViewingPaper] = useState<PaperInfo | null>(null)
  const [topicPapersList, setTopicPapersList] = useState<PaperInfo[]>([])

  const [searchOpen, setSearchOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const [showEmailModal, setShowEmailModal] = useState(false)
  const [pendingCitationCheck, setPendingCitationCheck] = useState(false)

  // Download tasks
  const [downloadTaskIds, setDownloadTaskIds] = useState<string[]>([])

  const handleTopicSelect = useCallback((name: string) => {
    baseHandleTopicSelect(name)
    setViewingPaper(null)
    setSelectedPapers(new Set())
    setTopicPapersList([])
  }, [baseHandleTopicSelect])

  // Bumped to signal components to reload data
  const [papersVersion, setPapersVersion] = useState(0)

  const handlePapersChanged = useCallback(() => {
    setPapersVersion(v => v + 1)
  }, [])

  const handlePapersLoaded = useCallback((papers: PaperInfo[]) => {
    setTopicPapersList(papers)
    setSelectedPapers(new Set(papers.map(p => p.arxiv_id)))
  }, [])

  const handlePaperClick = useCallback((paper: PaperInfo) => {
    setViewingPaper(paper)
  }, [])

  const handlePaperRemove = useCallback(async (arxivId: string) => {
    if (!activeTopic) return
    try {
      await api.papers.remove(activeTopic, arxivId)
      setPapersVersion(v => v + 1)
      setViewingPaper(null)
      setSelectedPapers(prev => {
        const next = new Set(prev)
        next.delete(arxivId)
        return next
      })
      showToast('Paper removed', 'success')
    } catch {
      showToast('Failed to remove paper', 'error')
    }
  }, [activeTopic])

  const handleClearHistory = useCallback(async () => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
    try {
      await api.history.clear(activeTopic)
      setHistoryVersion(v => v + 1)
      setTokens({ prompt: 0, completion: 0, total: 0 })
      api.contextBudget(activeTopic).then(setBudget).catch(() => {
        // Context budget may not be available
      })
      showToast('Conversation cleared', 'success')
    } catch {
      showToast('Failed to clear conversation', 'error')
    }
  }, [activeTopic, setBudget, setHistoryVersion, setTokens])

  const handleExport = useCallback(async () => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
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

  const handleCheckCitations = useCallback(() => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
    if (selectedPapers.size === 0) {
      showToast('Select papers to check', 'warning')
      return
    }

    // Show email modal if no decision yet
    if (!hasEmailDecision()) {
      setPendingCitationCheck(true)
      setShowEmailModal(true)
      return
    }

    // Proceed with check
    setCitationChecking(true)
    setCitationProgress(null)
    setCitationReport(null)
    setCitationError(null)
    const email = getStoredEmail()
    send({
      type: 'check_citations',
      topic: activeTopic,
      paper_ids: Array.from(selectedPapers),
      ...(email ? { polite_email: email } : {}),
    })
  }, [activeTopic, selectedPapers, send])

  const handleEmailSubmit = useCallback((email: string) => {
    setShowEmailModal(false)
    if (pendingCitationCheck) {
      setPendingCitationCheck(false)
      setCitationChecking(true)
      setCitationProgress(null)
      setCitationReport(null)
      setCitationError(null)
      send({
        type: 'check_citations',
        topic: activeTopic!,
        paper_ids: Array.from(selectedPapers),
        polite_email: email,
      })
    }
  }, [activeTopic, selectedPapers, send, pendingCitationCheck])

  const handleEmailSkip = useCallback(() => {
    setShowEmailModal(false)
    if (pendingCitationCheck) {
      setPendingCitationCheck(false)
      setCitationChecking(true)
      setCitationProgress(null)
      setCitationReport(null)
      setCitationError(null)
      send({
        type: 'check_citations',
        topic: activeTopic!,
        paper_ids: Array.from(selectedPapers),
      })
    }
  }, [activeTopic, selectedPapers, send, pendingCitationCheck])

  const handleDownloadStarted = useCallback((taskId: string) => {
    setDownloadTaskIds(prev => [...prev, taskId])
  }, [])

  const handleDownloadComplete = useCallback((taskId: string) => {
    setDownloadTaskIds(prev => prev.filter(id => id !== taskId))
    handlePapersChanged()
  }, [handlePapersChanged])

  return (
    <AppShell connected={connected}>
      <Header
        onSearchToggle={() => setSearchOpen(s => !s)}
        onCheckCitations={handleCheckCitations}
        onExport={handleExport}
        onHelpToggle={() => setHelpOpen(h => !h)}
        dark={dark}
        onThemeToggle={toggleTheme}
      />

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        <TopicSidebar
          activeTopic={activeTopic}
          onSelectTopic={handleTopicSelect}
          onTopicsChange={() => {}}
          refreshKey={papersVersion}
          selectedPapers={selectedPapers}
          onSelectionChange={setSelectedPapers}
          onPaperClick={handlePaperClick}
          onPapersLoaded={handlePapersLoaded}
          viewingPaperId={viewingPaper?.arxiv_id}
          style={{ width: sidebarWidth }}
        />

        {/* Resize handle */}
        <div
          onMouseDown={handleSidebarDrag}
          className="w-1 cursor-col-resize hover:bg-accent/30 active:bg-accent/50 transition-colors shrink-0"
        />

        {/* Center column */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {viewingPaper && (
            <PaperDetail
              paper={viewingPaper}
              topicName={activeTopic ?? ''}
              onRemove={handlePaperRemove}
              onClose={() => setViewingPaper(null)}
            />
          )}
          <div className={`flex-1 flex flex-col min-w-0 min-h-0 ${viewingPaper ? 'hidden' : ''}`}>
            <ChatArea
              topicName={activeTopic}
              connected={connected}
              wsSend={send}
              wsOnMessage={onMessage}
              onViewTrace={handleViewTrace}
              onClearHistory={handleClearHistory}
              historyVersion={historyVersion}
              selectedPapers={selectedPapers}
              topicPapers={topicPapersList}
              onPaperClick={handlePaperClick}
            />
          </div>
        </div>

        {/* Right panels */}
        {searchOpen && (
          <SearchPanel activeTopic={activeTopic} onClose={() => setSearchOpen(false)} onPapersChanged={handlePapersChanged} onDownloadStarted={handleDownloadStarted} />
        )}
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

      {helpOpen && <HelpPanel onClose={() => setHelpOpen(false)} />}

      <CitationReport
        checking={citationChecking}
        progress={citationProgress}
        report={citationReport}
        error={citationError}
        onClose={() => {
          setCitationChecking(false)
          setCitationReport(null)
          setCitationError(null)
        }}
      />

      {showEmailModal && (
        <EmailModal onSubmit={handleEmailSubmit} onSkip={handleEmailSkip} />
      )}

      <DownloadProgress
        taskIds={downloadTaskIds}
        onComplete={handleDownloadComplete}
      />

      <ToastContainer />
    </AppShell>
  )
}
