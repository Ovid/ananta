import type { ReactNode } from 'react'
import Markdown from 'react-markdown'

import { mdComponents } from './mdComponents'
import type { Exchange } from '../types'
import { stripBoundaryMarkers } from '../utils/sanitize'

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

interface ChatMessageProps {
  exchange: Exchange
  onViewTrace: (traceId: string) => void
  renderAnswer?: (answer: string) => ReactNode
  answerFooter?: ReactNode
}

export type { ChatMessageProps }

export default function ChatMessage({ exchange, onViewTrace, renderAnswer, answerFooter }: ChatMessageProps) {
  const questionTime = formatTime(exchange.timestamp)
  // Estimate answer time by adding execution_time to the question timestamp
  const answerTime = formatTime(
    new Date(new Date(exchange.timestamp).getTime() + exchange.execution_time * 1000).toISOString()
  )

  return (
    <div className="flex flex-col gap-3 py-3">
      {/* User question */}
      <div className="flex flex-col items-end gap-0.5">
        <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
          {exchange.question}
        </div>
        <span className="text-[10px] text-text-dim mr-1">{questionTime}</span>
      </div>

      {/* Assistant answer */}
      <div className="flex flex-col items-start gap-0.5">
        <div className="max-w-[70%] bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary">
          <div>
            {renderAnswer
              ? renderAnswer(exchange.answer)
              : <Markdown components={mdComponents}>{stripBoundaryMarkers(exchange.answer)}</Markdown>}
          </div>

          {answerFooter}

          <div className="flex items-center gap-3 mt-2 text-[10px] text-text-dim">
            <span>{exchange.tokens.total} tokens</span>
            <span>{exchange.execution_time.toFixed(1)}s</span>
            {exchange.trace_id && (
              <button
                onClick={() => onViewTrace(exchange.trace_id!)}
                className="text-accent hover:underline"
              >
                View trace
              </button>
            )}
          </div>
        </div>
        <span className="text-[10px] text-text-dim ml-1">{answerTime}</span>
      </div>
    </div>
  )
}
