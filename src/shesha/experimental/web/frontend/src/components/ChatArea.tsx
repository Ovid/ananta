import type { ReactNode } from 'react'
import { useCallback } from 'react'

import { ChatArea as SharedChatArea } from '@shesha/shared-ui'
import type { Exchange as SharedExchange, WSMessage as SharedWSMessage } from '@shesha/shared-ui'
import { api } from '../api/client'
import type { Exchange, PaperInfo, WSMessage } from '../types'

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
  // Translate arxiv-specific paper_ids to shared document_ids in history
  const loadHistory = useCallback(async (topic: string): Promise<SharedExchange[]> => {
    const data = await api.history.get(topic)
    return data.exchanges.map((ex: Exchange) => ({
      exchange_id: ex.exchange_id,
      question: ex.question,
      answer: ex.answer,
      trace_id: ex.trace_id,
      timestamp: ex.timestamp,
      tokens: ex.tokens,
      execution_time: ex.execution_time,
      model: ex.model,
      document_ids: ex.paper_ids,
    }))
  }, [])

  // Adapt wsOnMessage to filter through shared WSMessage types.
  // The arxiv WebSocket sends paper_ids on complete, but the shared component
  // only cares about the base message types (status, step, complete, error, cancelled).
  const sharedWsOnMessage = useCallback(
    (fn: (msg: SharedWSMessage) => void) => {
      return wsOnMessage((msg: WSMessage) => {
        if (msg.type === 'status' || msg.type === 'step' || msg.type === 'error' || msg.type === 'cancelled') {
          fn(msg)
        } else if (msg.type === 'complete') {
          fn({
            type: 'complete',
            answer: msg.answer,
            trace_id: msg.trace_id,
            tokens: msg.tokens,
            duration_ms: msg.duration_ms,
            document_ids: msg.paper_ids,
          })
        }
        // citation_progress and citation_report are arxiv-specific; not forwarded
      })
    },
    [wsOnMessage],
  )

  // Build citation renderer using current topicPapers context
  const renderAnswer = useCallback(
    (answer: string): ReactNode => (
      <>{renderAnswerWithCitations(answer, topicPapers, onPaperClick)}</>
    ),
    [topicPapers, onPaperClick],
  )

  // Build consulted papers footer per exchange
  const renderAnswerFooter = useCallback(
    (exchange: SharedExchange): ReactNode => {
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
