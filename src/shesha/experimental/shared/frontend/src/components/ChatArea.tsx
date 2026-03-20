import { useState, useEffect, useRef, useCallback, type KeyboardEvent, type ReactNode } from 'react'
import Markdown from 'react-markdown'

import { showToast } from './Toast'
import ChatMessage from './ChatMessage'
import { mdComponents } from './mdComponents'
import type { Exchange, WSMessage } from '../types'

interface ChatAreaProps {
  topicName: string | null
  connected: boolean
  wsSend: (data: object) => void
  wsOnMessage: (fn: (msg: WSMessage) => void) => () => void
  onViewTrace: (traceId: string) => void
  onClearHistory: () => void
  historyVersion: number
  selectedDocuments?: Set<string>
  emptySelectionMessage?: string
  placeholder?: string
  loadHistory: (topic: string) => Promise<Exchange[]>
  renderAnswer?: (answer: string) => ReactNode
  renderAnswerFooter?: (exchange: Exchange) => ReactNode
  allowBackgroundKnowledge?: boolean
}

export type { ChatAreaProps }

/**
 * Predefined prompt sent when the user clicks the "More" button.
 * Asks the system to verify, enhance, and re-present its previous analysis.
 * Referenced by Requirement 3.2 in the explorer-more-button spec.
 */
export const DEEPER_ANALYSIS_PROMPT =
  'Do a deeper dive to verify if your report is complete, accurate, and relevant. ' +
  'Explain any changes or additions in bullet points and then present the full report ' +
  'with those changes and/or additions. You must also walk through the entire report, ' +
  'point by point, and ensure its aligned with the previous report and the changes or additions.'

/**
 * Prompt sent when the previous exchange ended in a give-up ("I cannot answer").
 * Instructs the RLM to try fundamentally different search strategies.
 */
export const RETRY_SEARCH_PROMPT =
  'The previous attempt could not answer the question. ' +
  'Try a fundamentally different exploration strategy — search for different ' +
  'keywords, examine different sections of the documents, or restructure your ' +
  'sub-LLM queries. Do not repeat the same approaches.'

/**
 * Select the appropriate prompt for the "More" button based on conversation context.
 *
 * When the last exchange has the gave_up flag set (indicating the RLM called
 * PARTIAL instead of FINAL), returns a retry-focused prompt. Otherwise returns
 * the default deeper-analysis prompt. After one retry, the new exchange has
 * gave_up=false, so subsequent clicks naturally revert to the default prompt.
 */
export function getMorePrompt(exchanges: Exchange[]): string {
  if (exchanges[exchanges.length - 1]?.gave_up) {
    return RETRY_SEARCH_PROMPT
  }
  return DEEPER_ANALYSIS_PROMPT
}

export default function ChatArea({
  topicName,
  connected,
  wsSend,
  wsOnMessage,
  onViewTrace,
  onClearHistory,
  historyVersion,
  selectedDocuments,
  emptySelectionMessage = 'Select documents in the sidebar first...',
  placeholder = 'Ask a question...',
  loadHistory,
  renderAnswer,
  renderAnswerFooter,
  allowBackgroundKnowledge = false,
}: ChatAreaProps) {
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [pendingSentAt, setPendingSentAt] = useState<string>('')
  const [phase, setPhase] = useState('')
  const [showBanner, setShowBanner] = useState(() => {
    return localStorage.getItem('shesha-welcome-dismissed') !== 'true'
  })
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea on input change (floor at 2.25rem / 36px = h-9)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0'
    el.style.height = Math.max(36, el.scrollHeight) + 'px'
  }, [input])

  // Load history when topic changes
  useEffect(() => {
    if (!topicName) {
      setExchanges([])
      return
    }
    loadHistory(topicName).then(data => {
      setExchanges(data)
    }).catch(() => {
      showToast('Failed to load conversation history', 'error')
    })
  }, [topicName, historyVersion, loadHistory])

  // Listen for WebSocket messages
  useEffect(() => {
    return wsOnMessage((msg: WSMessage) => {
      if (msg.type === 'status') {
        setPhase(msg.phase)
      } else if (msg.type === 'step') {
        setPhase(`${msg.step_type} (iter ${msg.iteration})`)
      } else if (msg.type === 'complete') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
        // Reload history to get the saved exchange
        if (topicName) {
          loadHistory(topicName).then(data => {
            setExchanges(data)
          }).catch(() => {
            // History reload failed after completion; exchanges may be stale
          })
        }
      } else if (msg.type === 'error') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
        showToast(msg.message, 'error')
      } else if (msg.type === 'cancelled') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
      }
    })
  }, [wsOnMessage, topicName, loadHistory])

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [exchanges, thinking])

  const hasDocuments = selectedDocuments != null && selectedDocuments.size > 0

  /** Send button requires non-empty input plus all shared preconditions. */
  const canSend = !!input.trim() && !!topicName && !thinking && connected && hasDocuments

  /**
   * More button enabled when all shared preconditions are met:
   * - A topic is selected (topicName is truthy)
   * - Not currently processing a query (!thinking)
   * - WebSocket is connected
   * - At least one document is selected (hasDocuments)
   *
   * Unlike canSend, this does NOT require text in the textarea since the
   * More button sends the predefined DEEPER_ANALYSIS_PROMPT.
   * See Requirements 2.1–2.5 in the explorer-more-button spec.
   */
  const canSendMore = !!topicName && !thinking && connected && hasDocuments && exchanges.length > 0

  /**
   * Sends a query message via WebSocket and updates UI state.
   * Shared by both the Send button (user-typed question) and the More button (predefined prompt).
   */
  const sendQuery = useCallback((question: string) => {
    if (!selectedDocuments) return
    const msg: Record<string, unknown> = {
      type: 'query',
      topic: topicName,
      question,
      document_ids: Array.from(selectedDocuments),
      allow_background_knowledge: allowBackgroundKnowledge,
    }
    wsSend(msg)
    setPendingQuestion(question)
    setPendingSentAt(new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
    setThinking(true)
    setPhase('Starting')
  }, [topicName, wsSend, selectedDocuments, allowBackgroundKnowledge])

  /** Sends the user-typed question from the textarea. */
  const handleSend = useCallback(() => {
    if (!canSend) return
    sendQuery(input.trim())
    setInput('')
  }, [canSend, input, sendQuery])

  /** Sends the predefined deeper-analysis prompt with one click. */
  const handleMore = useCallback(() => {
    if (!canSendMore) return
    sendQuery(getMorePrompt(exchanges))
  }, [canSendMore, sendQuery, exchanges])

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    if (e.key === 'Escape' && thinking) {
      wsSend({ type: 'cancel' })
    }
  }

  const dismissBanner = () => {
    setShowBanner(false)
    localStorage.setItem('shesha-welcome-dismissed', 'true')
  }

  if (!topicName) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-dim text-sm">
        Select or create a topic to begin.
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Experimental welcome banner */}
      {showBanner && (
        <div className="bg-amber/5 border-b border-amber/20 px-4 py-2 flex items-center justify-between text-xs text-amber">
          <span>
            This is experimental software. Some features may be incomplete.
            Click the <strong>?</strong> icon in the header for help.
          </span>
          <button onClick={dismissBanner} className="ml-2 hover:text-amber/80">&times;</button>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 px-4">
        {exchanges.length === 0 && !thinking && (
          <div className="flex items-center justify-center h-full text-text-dim text-sm">
            Ask a question about the documents in this topic.
          </div>
        )}
        {exchanges.map(ex => (
          <ChatMessage key={ex.exchange_id} exchange={ex} onViewTrace={onViewTrace} renderAnswer={renderAnswer} answerFooter={renderAnswerFooter?.(ex)} />
        ))}

        {/* Pending question (shown immediately before answer arrives) */}
        {pendingQuestion && (
          <div className="flex flex-col gap-3 py-3">
            <div className="flex flex-col items-end gap-0.5">
              <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
                <Markdown components={mdComponents}>{pendingQuestion}</Markdown>
              </div>
              <span className="text-[10px] text-text-dim mr-1">{pendingSentAt}</span>
            </div>
          </div>
        )}

        {/* Thinking indicator */}
        {thinking && (
          <div className="flex justify-start py-3">
            <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-dim">
              <span className="inline-flex gap-1">
                <span className="animate-bounce" style={{ animationDelay: '0ms' }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: '150ms' }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: '300ms' }}>.</span>
              </span>
              {phase && <span className="ml-2 text-xs">{phase}</span>}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border bg-surface-1 px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!connected || !hasDocuments}
            placeholder={
              !connected ? 'Reconnecting...'
              : !hasDocuments ? emptySelectionMessage
              : placeholder
            }
            style={{ height: '36px', maxHeight: '6rem' }}
            className="flex-1 bg-surface-2 border border-border rounded px-3 py-1.5 text-sm leading-5 text-text-primary resize-none overflow-y-auto focus:outline-none focus:border-accent disabled:opacity-50"
          />
          {thinking ? (
            <button
              onClick={() => wsSend({ type: 'cancel' })}
              className="w-20 h-9 border border-transparent bg-red text-white rounded text-sm font-medium hover:bg-red/90 transition-colors"
            >
              Cancel
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              className="w-20 h-9 border border-transparent bg-accent text-surface-0 rounded text-sm font-medium hover:bg-accent/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Send
            </button>
          )}
          {!thinking && (
            <button
              onClick={handleMore}
              disabled={!canSendMore}
              aria-label="Request deeper analysis"
              aria-disabled={!canSendMore}
              className="w-20 h-9 bg-surface-2 border border-border text-text-primary rounded text-sm font-medium hover:bg-surface-3 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              More
            </button>
          )}
          <button
            onClick={onClearHistory}
            disabled={thinking}
            className="p-2 text-text-dim hover:text-red transition-colors disabled:opacity-30"
            title="Clear conversation"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
