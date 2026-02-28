import type { ReactNode } from 'react'
import Markdown, { defaultUrlTransform } from 'react-markdown'

import { ChatMessage as SharedChatMessage, stripBoundaryMarkers } from '@shesha/shared-ui'
import { preprocessCitations, buildCitationComponents } from '../utils/citations'
import type { Exchange, PaperInfo } from '../types'

interface ChatMessageProps {
  exchange: Exchange
  onViewTrace: (traceId: string) => void
  topicPapers?: PaperInfo[]
  onPaperClick?: (paper: PaperInfo) => void
}

export default function ChatMessage({ exchange, onViewTrace, topicPapers, onPaperClick }: ChatMessageProps) {
  const renderAnswer = (answer: string): ReactNode => {
    const components = buildCitationComponents(topicPapers, onPaperClick)
    return (
      <Markdown
        components={components}
        disallowedElements={['img']}
        urlTransform={(url) => url.startsWith('arxiv:') ? url : defaultUrlTransform(url)}
      >
        {preprocessCitations(stripBoundaryMarkers(answer))}
      </Markdown>
    )
  }

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
