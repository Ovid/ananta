import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import fc from 'fast-check'

beforeAll(() => {
  const store: Record<string, string> = {}
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k in store) delete store[k] },
    },
    configurable: true,
  })
  Element.prototype.scrollTo = vi.fn()
})

import ChatArea from '../ChatArea'
import type { ChatAreaProps } from '../ChatArea'

// Requirement 3.2: exact prompt text
const DEEPER_ANALYSIS_PROMPT =
  'Do a deeper dive to verify if your report is complete, accurate, and relevant. ' +
  'Explain any changes or additions in bullet points and then present the full report ' +
  'with those changes and/or additions. You must also walk through the entire report, ' +
  'point by point, and ensure its aligned with the previous report and the changes or additions.'

/** Default props for rendering ChatArea in a ready-to-interact state. */
function defaultProps(overrides: Partial<ChatAreaProps> = {}): ChatAreaProps {
  return {
    topicName: 'test-topic',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
    selectedDocuments: new Set(['doc-1']),
    loadHistory: vi.fn().mockResolvedValue([]),
    ...overrides,
  }
}

/** Render ChatArea with sensible defaults; returns the props used so tests can inspect mocks. */
async function renderChatArea(overrides: Partial<ChatAreaProps> = {}) {
  const props = defaultProps(overrides)
  await act(async () => {
    render(<ChatArea {...props} />)
  })
  return props
}

describe('ChatArea (shared) - no topic', () => {
  it('shows placeholder when no topic is selected', async () => {
    await act(async () => {
      render(
        <ChatArea
          topicName={null}
          connected={true}
          wsSend={vi.fn()}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          loadHistory={vi.fn().mockResolvedValue([])}
        />
      )
    })
    expect(screen.getByText('Select or create a topic to begin.')).toBeInTheDocument()
  })
})

describe('ChatArea (shared) - input disabled state', () => {
  const baseProps = {
    topicName: 'chess',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
    loadHistory: vi.fn().mockResolvedValue([]),
  }

  it('disables textarea when no documents are selected', async () => {
    await act(async () => {
      render(
        <ChatArea
          {...baseProps}
          selectedDocuments={new Set()}
          emptySelectionMessage="Select documents in the sidebar first..."
        />
      )
    })
    const textarea = screen.getByPlaceholderText('Select documents in the sidebar first...')
    expect(textarea).toBeDisabled()
  })

  it('enables textarea when documents are selected', async () => {
    await act(async () => {
      render(
        <ChatArea
          {...baseProps}
          selectedDocuments={new Set(['doc-1'])}
        />
      )
    })
    const textarea = screen.getByPlaceholderText('Ask a question...')
    expect(textarea).not.toBeDisabled()
  })

  it('uses custom placeholder text', async () => {
    await act(async () => {
      render(
        <ChatArea
          {...baseProps}
          selectedDocuments={new Set(['doc-1'])}
          placeholder="Ask about your code..."
        />
      )
    })
    expect(screen.getByPlaceholderText('Ask about your code...')).toBeInTheDocument()
  })

  it('defaults placeholder to "Ask a question..." when not provided', async () => {
    await act(async () => {
      render(
        <ChatArea
          {...baseProps}
          selectedDocuments={new Set(['doc-1'])}
        />
      )
    })
    expect(screen.getByPlaceholderText('Ask a question...')).toBeInTheDocument()
  })
})

describe('ChatArea (shared) - sends document_ids in query', () => {
  it('sends document_ids array in WebSocket message', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()

    await act(async () => {
      render(
        <ChatArea
          topicName="chess"
          connected={true}
          wsSend={wsSend}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          selectedDocuments={new Set(['doc-1', 'doc-2'])}
          loadHistory={vi.fn().mockResolvedValue([])}
        />
      )
    })

    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'What is chess?')
    await user.click(screen.getByText('Send'))

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        topic: 'chess',
        question: 'What is chess?',
        document_ids: expect.arrayContaining(['doc-1', 'doc-2']),
      })
    )
  })
})

describe('ChatArea (shared) - thinking state', () => {
  it('shows thinking indicator and pending question after send', async () => {
    const user = userEvent.setup()

    await act(async () => {
      render(
        <ChatArea
          topicName="chess"
          connected={true}
          wsSend={vi.fn()}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          selectedDocuments={new Set(['doc-1'])}
          loadHistory={vi.fn().mockResolvedValue([])}
        />
      )
    })

    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'Hello')
    await user.click(screen.getByText('Send'))

    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.getByText('Starting')).toBeInTheDocument()
  })
})

describe('ChatArea (shared) - cancel', () => {
  it('sends cancel message when Cancel button is clicked', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()

    await act(async () => {
      render(
        <ChatArea
          topicName="chess"
          connected={true}
          wsSend={wsSend}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          selectedDocuments={new Set(['doc-1'])}
          loadHistory={vi.fn().mockResolvedValue([])}
        />
      )
    })

    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'Hello')
    await user.click(screen.getByText('Send'))

    // After sending, Cancel button should appear
    await user.click(screen.getByText('Cancel'))

    expect(wsSend).toHaveBeenCalledWith({ type: 'cancel' })
  })
})

describe('ChatArea (shared) - renderAnswer passthrough', () => {
  const sampleExchange = {
    exchange_id: 'ex-1',
    question: 'Q?',
    answer: 'A!',
    timestamp: '2026-02-13T12:00:00Z',
    tokens: { prompt: 10, completion: 5, total: 15 },
    execution_time: 1.0,
    trace_id: null,
    model: 'test',
    document_ids: ['doc-1'],
  }

  it('passes renderAnswer to ChatMessage components', async () => {
    const renderAnswer = (answer: string) => <span data-testid="custom">{answer}</span>

    await act(async () => {
      render(
        <ChatArea
          topicName="chess"
          connected={true}
          wsSend={vi.fn()}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          selectedDocuments={new Set(['doc-1'])}
          loadHistory={vi.fn().mockResolvedValue([sampleExchange])}
          renderAnswer={renderAnswer}
        />
      )
    })

    expect(screen.getByTestId('custom')).toBeInTheDocument()
  })

  it('passes renderAnswerFooter to ChatMessage components', async () => {
    const renderAnswerFooter = () => <div data-testid="exchange-footer">Extra</div>

    await act(async () => {
      render(
        <ChatArea
          topicName="chess"
          connected={true}
          wsSend={vi.fn()}
          wsOnMessage={vi.fn().mockReturnValue(() => {})}
          onViewTrace={vi.fn()}
          onClearHistory={vi.fn()}
          historyVersion={0}
          selectedDocuments={new Set(['doc-1'])}
          loadHistory={vi.fn().mockResolvedValue([sampleExchange])}
          renderAnswerFooter={renderAnswerFooter}
        />
      )
    })

    expect(screen.getByTestId('exchange-footer')).toBeInTheDocument()
  })
})

describe('ChatArea (shared) - auto-growing textarea', () => {
  const baseProps = {
    topicName: 'chess',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
    selectedDocuments: new Set(['doc-1']),
    loadHistory: vi.fn().mockResolvedValue([]),
  }

  it('textarea has max-height set to 6rem', async () => {
    await act(async () => {
      render(<ChatArea {...baseProps} />)
    })
    const textarea = screen.getByPlaceholderText('Ask a question...')
    expect(textarea).toHaveStyle({ maxHeight: '6rem' })
  })

  it('textarea resets value after sending', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ChatArea {...baseProps} />)
    })
    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'Hello world')
    expect(textarea).toHaveValue('Hello world')
    await user.click(screen.getByText('Send'))
    expect(textarea).toHaveValue('')
  })
})

describe('ChatArea (shared) - More button test infrastructure', () => {
  it('DEEPER_ANALYSIS_PROMPT matches the required text', () => {
    expect(DEEPER_ANALYSIS_PROMPT).toBe(
      'Do a deeper dive to verify if your report is complete, accurate, and relevant. ' +
      'Explain any changes or additions in bullet points and then present the full report ' +
      'with those changes and/or additions. You must also walk through the entire report, ' +
      'point by point, and ensure its aligned with the previous report and the changes or additions.'
    )
  })

  it('renderChatArea helper renders with default props', async () => {
    await renderChatArea()
    expect(screen.getByPlaceholderText('Ask a question...')).toBeInTheDocument()
  })

  it('renderChatArea helper accepts prop overrides', async () => {
    const wsSend = vi.fn()
    const props = await renderChatArea({ wsSend })
    expect(props.wsSend).toBe(wsSend)
  })

  it('fast-check is available for property-based tests', () => {
    // Smoke test: generate a small batch of booleans to confirm fc works
    fc.assert(fc.property(fc.boolean(), (b) => typeof b === 'boolean'), { numRuns: 10 })
  })
})
