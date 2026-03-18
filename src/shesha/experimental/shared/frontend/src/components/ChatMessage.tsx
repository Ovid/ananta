import type { ReactNode } from 'react'
import Markdown from 'react-markdown'

import { mdComponents } from './mdComponents'
import type { Exchange } from '../types'
import { splitAugmentedSections } from '../utils/augmented'
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
          <Markdown components={mdComponents}>{exchange.question}</Markdown>
        </div>
        <span className="text-[10px] text-text-dim mr-1">{questionTime}</span>
      </div>

      {/* Assistant answer */}
      <div className="flex flex-col items-start gap-0.5">
        <div className="max-w-[70%] bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary">
          <div>
            {renderAnswer
              ? renderAnswer(exchange.answer)
              : (() => {
                  const sanitized = stripBoundaryMarkers(exchange.answer)
                  const sections = splitAugmentedSections(sanitized)
                  const hasBackground = sections.some(s => s.type === 'background')
                  if (!hasBackground) {
                    return <Markdown components={mdComponents}>{sanitized}</Markdown>
                  }
                  return (
                    <>
                      {sections.map((section, i) =>
                        section.type === 'document' ? (
                          <Markdown key={i} components={mdComponents}>{section.content}</Markdown>
                        ) : (
                          <aside
                            key={i}
                            role="complementary"
                            aria-label="Background knowledge"
                            className="my-3 pl-3 py-2 pr-2 border-l-[3px] border-amber bg-amber/5 dark:bg-amber/10 rounded-r"
                          >
                            <span className="block text-[10px] font-medium text-amber mb-1 uppercase tracking-wide">
                              Background knowledge
                            </span>
                            <Markdown components={mdComponents}>{section.content}</Markdown>
                          </aside>
                        )
                      )}
                    </>
                  )
                })()}
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
