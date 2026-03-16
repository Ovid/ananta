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

describe('ChatArea (shared) - More button rendering', () => {
  it('renders a button with text "More"', async () => {
    await renderChatArea()
    expect(screen.getByRole('button', { name: /deeper analysis/i })).toBeInTheDocument()
  })

  it('positions More button between textarea and Send button', async () => {
    await renderChatArea()
    const textarea = screen.getByPlaceholderText('Ask a question...')
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    const sendBtn = screen.getByRole('button', { name: /send/i })

    // All three should share the same parent flex container
    const container = textarea.parentElement!
    const children = Array.from(container.children)
    const textareaIdx = children.indexOf(textarea)
    const moreIdx = children.indexOf(moreBtn)
    const sendIdx = children.indexOf(sendBtn)

    expect(moreIdx).toBeGreaterThan(textareaIdx)
    expect(moreIdx).toBeLessThan(sendIdx)
  })

  it('hides More button when thinking is true', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    // Type and send to enter thinking state
    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'Hello')
    await user.click(screen.getByRole('button', { name: /send/i }))

    // Now in thinking state — More button should not be in the DOM
    expect(screen.queryByRole('button', { name: /deeper analysis/i })).not.toBeInTheDocument()
  })
})

describe('ChatArea (shared) - More button enablement', () => {
  it('disables More button when connected=false', async () => {
    await renderChatArea({ connected: false })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).toBeDisabled()
  })

  it('disables More button when selectedDocuments is undefined', async () => {
    await renderChatArea({ selectedDocuments: undefined })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).toBeDisabled()
  })

  it('disables More button when selectedDocuments is empty Set', async () => {
    await renderChatArea({ selectedDocuments: new Set() })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).toBeDisabled()
  })

  it('disables More button when topicName is null', async () => {
    await renderChatArea({ topicName: null })
    // When topicName is null, the component renders a placeholder view
    // and the More button should not be present at all
    expect(screen.queryByRole('button', { name: /deeper analysis/i })).not.toBeInTheDocument()
  })

  it('enables More button when all conditions met (connected, has documents, has topic, not thinking)', async () => {
    await renderChatArea({
      connected: true,
      selectedDocuments: new Set(['doc-1']),
      topicName: 'test-topic',
    })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).not.toBeDisabled()
  })
})

describe('ChatArea (shared) - More button click behavior', () => {
  it('calls wsSend with correct message structure when More is clicked', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({
      wsSend,
      topicName: 'my-topic',
      selectedDocuments: new Set(['doc-a', 'doc-b']),
      connected: true,
    })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        topic: 'my-topic',
        question: DEEPER_ANALYSIS_PROMPT,
        document_ids: expect.arrayContaining(['doc-a', 'doc-b']),
      })
    )
  })

  it('clears textarea content when More is clicked', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'some draft text')
    expect(textarea).toHaveValue('some draft text')

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    expect(textarea).toHaveValue('')
  })

  it('sets thinking state to true when More is clicked (Cancel button appears)', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // Thinking state means Cancel button replaces Send, and More disappears
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /deeper analysis/i })).not.toBeInTheDocument()
  })

  it('sets pendingQuestion to DEEPER_ANALYSIS_PROMPT when More is clicked', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // The pending question text should appear in the chat area
    // Markdown renders the text inside a <p>, so both the <p> and its parent <div> match.
    // Use getAllByText and assert at least one match.
    const matches = screen.getAllByText((_content, element) => {
      return element?.textContent === DEEPER_ANALYSIS_PROMPT
    })
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('sets pendingSentAt timestamp when More is clicked', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    const before = new Date()
    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // A timestamp string should appear near the pending question (format: "H:MM AM/PM")
    const timePattern = /\d{1,2}:\d{2}\s*[AP]M/i
    const allText = document.body.textContent ?? ''
    expect(allText).toMatch(timePattern)
  })
})

describe('ChatArea (shared) - More button accessibility', () => {
  it('has correct tab order: textarea → More → Send → Clear', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    // Type text so Send button is enabled and participates in tab order
    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'hello')

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    const sendBtn = screen.getByRole('button', { name: /send/i })
    const clearBtn = screen.getByTitle('Clear conversation')

    // Start focus on textarea, then tab through
    textarea.focus()
    expect(document.activeElement).toBe(textarea)

    await user.tab()
    expect(document.activeElement).toBe(moreBtn)

    await user.tab()
    expect(document.activeElement).toBe(sendBtn)

    await user.tab()
    expect(document.activeElement).toBe(clearBtn)
  })

  it('has visible focus indicator (focus ring classes)', async () => {
    await renderChatArea()
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

    expect(moreBtn.className).toMatch(/focus:ring-2/)
    expect(moreBtn.className).toMatch(/focus:ring-accent/)
    expect(moreBtn.className).toMatch(/focus:ring-offset-2/)
  })

  it('has aria-label="Request deeper analysis"', async () => {
    await renderChatArea()
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

    expect(moreBtn).toHaveAttribute('aria-label', 'Request deeper analysis')
  })

  it('has aria-disabled=false when button is enabled', async () => {
    await renderChatArea({
      connected: true,
      selectedDocuments: new Set(['doc-1']),
      topicName: 'test-topic',
    })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

    expect(moreBtn).toHaveAttribute('aria-disabled', 'false')
  })

  it('has aria-disabled=true when button is disabled', async () => {
    await renderChatArea({ connected: false })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

    expect(moreBtn).toHaveAttribute('aria-disabled', 'true')
  })

  it('activates handleMore when Enter key is pressed while focused', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({ wsSend })

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    moreBtn.focus()

    await user.keyboard('{Enter}')

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        question: DEEPER_ANALYSIS_PROMPT,
      })
    )
  })

  it('activates handleMore when Space key is pressed while focused', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({ wsSend })

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    moreBtn.focus()

    await user.keyboard(' ')

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        question: DEEPER_ANALYSIS_PROMPT,
      })
    )
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
