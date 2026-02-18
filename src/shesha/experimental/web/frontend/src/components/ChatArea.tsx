import type { ReactNode } from 'react'
import { useCallback } from 'react'

import { ChatArea as SharedChatArea, stripBoundaryMarkers } from '@shesha/shared-ui'
import type { Exchange, WSMessage as SharedWSMessage } from '@shesha/shared-ui'
import { api } from '../api/client'
import type { PaperInfo, WSMessage } from '../types'

const CITATION_RE = /\[@arxiv:([^\]]+)\]/g
const ARXIV_ID_RE = /(?:[\w.-]+\/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?/g

function renderAnswerWithCitations(
  text: string,
  topicPapers?: PaperInfo[],
  onPaperClick?: (paper: PaperInfo) => void,
): ReactNode[] {
  const parts: ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(CITATION_RE)) {
    const rawContent = match[1]
    const matchStart = match.index!

    // Add text before this match
    if (matchStart > lastIndex) {
      parts.push(text.slice(lastIndex, matchStart))
    }

    // Extract all arxiv IDs from the tag (handles semicolon-separated IDs)
    const ids = [...rawContent.matchAll(ARXIV_ID_RE)].map(m => m[0])

    if (ids.length === 0) {
      // No valid IDs found — render as literal text
      parts.push(match[0])
    } else {
      for (const arxivId of ids) {
        const paper = topicPapers?.find(p => p.arxiv_id === arxivId)
        if (paper) {
          parts.push(
            <button
              key={`cite-${matchStart}-${arxivId}`}
              onClick={() => onPaperClick?.(paper)}
              className="text-xs text-accent hover:underline bg-accent/5 rounded px-1 py-0.5 mx-0.5 inline"
              title={paper.title}
            >
              {paper.arxiv_id}
            </button>
          )
        } else {
          parts.push(`[@arxiv:${arxivId}]`)
        }
      }
    }

    lastIndex = matchStart + match[0].length
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
}

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

  // Build citation renderer using current topicPapers context
  const renderAnswer = useCallback(
    (answer: string): ReactNode => (
      <>{renderAnswerWithCitations(stripBoundaryMarkers(answer), topicPapers, onPaperClick)}</>
    ),
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
