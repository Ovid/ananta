import type { ReactNode } from 'react'

import { ChatMessage as SharedChatMessage } from '@shesha/shared-ui'
import type { Exchange, PaperInfo } from '../types'

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

interface ChatMessageProps {
  exchange: Exchange
  onViewTrace: (traceId: string) => void
  topicPapers?: PaperInfo[]
  onPaperClick?: (paper: PaperInfo) => void
}

export default function ChatMessage({ exchange, onViewTrace, topicPapers, onPaperClick }: ChatMessageProps) {
  // Build the citation renderer
  const renderAnswer = (answer: string): ReactNode => (
    <>{renderAnswerWithCitations(answer, topicPapers, onPaperClick)}</>
  )

  // Resolve document_ids to PaperInfo objects for the consulted papers footer
  const consultedPapers = (exchange.document_ids ?? [])
    .map(id => topicPapers?.find(p => p.arxiv_id === id))
    .filter((p): p is PaperInfo => p != null)

  const answerFooter = consultedPapers.length > 0 ? (
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
  ) : undefined

  return (
    <SharedChatMessage
      exchange={exchange}
      onViewTrace={onViewTrace}
      renderAnswer={renderAnswer}
      answerFooter={answerFooter}
    />
  )
}
