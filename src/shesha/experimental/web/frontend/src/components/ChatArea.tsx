import type { ReactNode } from 'react'
import { useCallback } from 'react'
import Markdown, { defaultUrlTransform } from 'react-markdown'

import { ChatArea as SharedChatArea, stripBoundaryMarkers } from '@shesha/shared-ui'
import type { Exchange, WSMessage as SharedWSMessage } from '@shesha/shared-ui'
import { preprocessCitations, buildCitationComponents } from '../utils/citations'
import { api } from '../api/client'
import type { PaperInfo, WSMessage } from '../types'

interface ChatAreaProps {
  topicName: string | null
  connected: boolean
  wsSend: (data: object) => void
  wsOnMessage: (fn: (msg: WSMessage) => void) => () => void
  onViewTrace: (traceId: string) => void
  onClearHistory: () => void
  historyVersion: number
  selectedPapers?: Set<string>
  topicPapers?: PaperInfo[]
  onPaperClick?: (paper: PaperInfo) => void
}

export default function ChatArea({ topicName, connected, wsSend, wsOnMessage, onViewTrace, onClearHistory, historyVersion, selectedPapers, topicPapers, onPaperClick }: ChatAreaProps) {
  const loadHistory = useCallback(async (topic: string): Promise<Exchange[]> => {
    const data = await api.history.get(topic)
    return data.exchanges
  }, [])

  // Adapt wsOnMessage to filter through shared WSMessage types.
  // Citation-specific messages (citation_progress, citation_report) are not forwarded.
  const sharedWsOnMessage = useCallback(
    (fn: (msg: SharedWSMessage) => void) => {
      return wsOnMessage((msg: WSMessage) => {
        if (msg.type === 'status' || msg.type === 'step' || msg.type === 'complete' || msg.type === 'error' || msg.type === 'cancelled') {
          fn(msg)
        }
        // citation_progress and citation_report are arxiv-specific; not forwarded
      })
    },
    [wsOnMessage],
  )

  // Build Markdown citation renderer using current topicPapers context
  const renderAnswer = useCallback(
    (answer: string): ReactNode => {
      const components = buildCitationComponents(topicPapers, onPaperClick)
      return (
        <Markdown
          components={components}
          urlTransform={(url) => url.startsWith('arxiv:') ? url : defaultUrlTransform(url)}
        >
          {preprocessCitations(stripBoundaryMarkers(answer))}
        </Markdown>
      )
    },
    [topicPapers, onPaperClick],
  )

  // Build consulted papers footer per exchange
  const renderAnswerFooter = useCallback(
    (exchange: Exchange): ReactNode => {
      const consultedPapers = (exchange.document_ids ?? [])
        .map(id => topicPapers?.find(p => p.arxiv_id === id))
        .filter((p): p is PaperInfo => p != null)

      if (consultedPapers.length === 0) return undefined

      return (
        <div className="mt-2 pt-2 border-t border-border">
          <div className="text-[10px] text-text-dim mb-1">Consulted papers:</div>
          <div className="flex flex-wrap gap-1">
            {consultedPapers.map(paper => (
              <button
                key={paper.arxiv_id}
                onClick={() => onPaperClick?.(paper)}
                className="text-[10px] text-accent hover:underline bg-accent/5 rounded px-1.5 py-0.5"
                title={paper.title}
              >
                {paper.arxiv_id}
              </button>
            ))}
          </div>
        </div>
      )
    },
    [topicPapers, onPaperClick],
  )

  return (
    <SharedChatArea
      topicName={topicName}
      connected={connected}
      wsSend={wsSend}
      wsOnMessage={sharedWsOnMessage}
      onViewTrace={onViewTrace}
      onClearHistory={onClearHistory}
      historyVersion={historyVersion}
      selectedDocuments={selectedPapers}
      emptySelectionMessage="Select papers in the sidebar first..."
      placeholder="Ask a question..."
      loadHistory={loadHistory}
      renderAnswer={renderAnswer}
      renderAnswerFooter={renderAnswerFooter}
    />
  )
}
