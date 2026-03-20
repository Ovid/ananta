import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import fc from 'fast-check'

import { showToast } from '../Toast'
vi.mock('../Toast', () => ({ showToast: vi.fn() }))

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

import ChatArea, { DEEPER_ANALYSIS_PROMPT, RETRY_SEARCH_PROMPT, getMorePrompt } from '../ChatArea'
import type { ChatAreaProps } from '../ChatArea'

/**
 * Sample exchange for tests that need non-empty history (required for More button).
 * NOTE: The `gave_up` field is intentionally absent (defaults to undefined/falsy) —
 * this matters because getMorePrompt() checks the last exchange's gave_up flag
 * to decide which prompt the More button sends. Tests that use this fixture
 * implicitly test the "normal answer → DEEPER_ANALYSIS_PROMPT" path.
 */
const sampleExchangeForHistory = {
  exchange_id: 'ex-0',
  question: 'Prior question',
  answer: 'Prior answer',
  timestamp: '2026-02-13T12:00:00Z',
  tokens: { prompt: 10, completion: 5, total: 15 },
  execution_time: 1.0,
  trace_id: null,
  model: 'test',
  document_ids: ['doc-1'],
}

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
    loadHistory: vi.fn().mockResolvedValue([sampleExchangeForHistory]),
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

describe('ChatArea (shared) - input row button alignment', () => {
  it('input row flex container uses items-start so buttons stay fixed height', async () => {
    await renderChatArea()
    const textarea = screen.getByPlaceholderText('Ask a question...')
    const container = textarea.parentElement!
    expect(container.className).toContain('items-start')
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

  it('positions Send button before More button', async () => {
    await renderChatArea()
    const textarea = screen.getByPlaceholderText('Ask a question...')
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    const sendBtn = screen.getByRole('button', { name: /send/i })

    // All three should share the same parent flex container
    const container = textarea.parentElement!
    const children = Array.from(container.children)
    const textareaIdx = children.indexOf(textarea)
    const sendIdx = children.indexOf(sendBtn)
    const moreIdx = children.indexOf(moreBtn)

    expect(sendIdx).toBeGreaterThan(textareaIdx)
    expect(sendIdx).toBeLessThan(moreIdx)
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

  it('enables More button when all conditions met (connected, has documents, has topic, has exchanges, not thinking)', async () => {
    await renderChatArea({
      connected: true,
      selectedDocuments: new Set(['doc-1']),
      topicName: 'test-topic',
    })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).not.toBeDisabled()
  })

  it('disables More button when no prior exchanges exist', async () => {
    await renderChatArea({
      connected: true,
      selectedDocuments: new Set(['doc-1']),
      topicName: 'test-topic',
      loadHistory: vi.fn().mockResolvedValue([]),
    })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    expect(moreBtn).toBeDisabled()
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

  it('preserves textarea draft when More is clicked', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'some draft text')
    expect(textarea).toHaveValue('some draft text')

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    expect(textarea).toHaveValue('some draft text')
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

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // A timestamp string should appear near the pending question.
    // Accepts both 12-hour ("3:45 PM") and 24-hour ("15:45") locale formats.
    const timePattern = /\d{1,2}:\d{2}(\s*[AP]M)?/i
    const allText = document.body.textContent ?? ''
    expect(allText).toMatch(timePattern)
  })

  it('sends RETRY_SEARCH_PROMPT when last exchange was a give-up', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    const giveUpExchange = {
      ...sampleExchangeForHistory,
      answer: 'Found some evidence but not enough.',
      gave_up: true,
    }
    await renderChatArea({
      wsSend,
      loadHistory: vi.fn().mockResolvedValue([giveUpExchange]),
    })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        question: RETRY_SEARCH_PROMPT,
      })
    )
  })
})

describe('ChatArea (shared) - More button accessibility', () => {
  it('has correct tab order: textarea → Send → More → Clear', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    // Type text so Send button is enabled and participates in tab order
    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'hello')

    const sendBtn = screen.getByRole('button', { name: /send/i })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    const clearBtn = screen.getByTitle('Clear conversation')

    // Start focus on textarea, then tab through
    textarea.focus()
    expect(document.activeElement).toBe(textarea)

    await user.tab()
    expect(document.activeElement).toBe(sendBtn)

    await user.tab()
    expect(document.activeElement).toBe(moreBtn)

    await user.tab()
    expect(document.activeElement).toBe(clearBtn)
  })

  it('Send and More buttons have the same fixed width class', async () => {
    await renderChatArea()
    const sendBtn = screen.getByRole('button', { name: /send/i })
    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

    // Both buttons should share a fixed width class for equal sizing
    expect(sendBtn.className).toMatch(/w-20/)
    expect(moreBtn.className).toMatch(/w-20/)
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

  it('activates handleMore exactly once when Enter key is pressed while focused', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({ wsSend })

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    moreBtn.focus()

    await user.keyboard('{Enter}')

    expect(wsSend).toHaveBeenCalledTimes(1)
    expect(wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        question: DEEPER_ANALYSIS_PROMPT,
      })
    )
  })

  it('activates handleMore exactly once when Space key is pressed while focused', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({ wsSend })

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    moreBtn.focus()

    await user.keyboard(' ')

    expect(wsSend).toHaveBeenCalledTimes(1)
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
    fc.assert(fc.property(fc.boolean(), (b: boolean) => typeof b === 'boolean'), { numRuns: 10 })
  })
})

/**
 * Helper that creates a wsOnMessage mock which captures the registered handler.
 * Call `dispatch(msg)` to simulate a WebSocket message arriving from the server.
 */
function createWsOnMessage() {
  let handler: ((msg: import('../../types').WSMessage) => void) | null = null
  const wsOnMessage = vi.fn((fn: (msg: import('../../types').WSMessage) => void) => {
    handler = fn
    return () => { handler = null }
  })
  const dispatch = (msg: import('../../types').WSMessage) => {
    if (!handler) throw new Error('wsOnMessage handler not registered')
    handler(msg)
  }
  return { wsOnMessage, dispatch }
}

describe('ChatArea (shared) - Property 1: Button enablement preconditions', () => {
  // Feature: explorer-more-button, Property 1
  // For any ChatArea state, the More button is enabled iff:
  // connected && hasDocuments && hasTopic && hasExchanges && !thinking
  // Requirements: 2.1, 2.2, 2.4, 2.5

  // Arbitrary for selectedDocuments: undefined, empty Set, or non-empty Set
  const arbSelectedDocuments = fc.oneof(
    fc.constant(undefined),
    fc.constant(new Set<string>()),
    fc
      .uniqueArray(fc.string({ minLength: 1, maxLength: 8 }), { minLength: 1, maxLength: 5 })
      .map((ids: string[]) => new Set(ids)),
  )

  // Arbitrary for topicName: null or a non-empty string
  const arbTopicName = fc.oneof(
    fc.constant(null),
    fc.string({ minLength: 1, maxLength: 20 }),
  )

  it('button enabled iff connected && hasDocuments && hasTopic && hasExchanges && !thinking', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.boolean(),           // connected
        arbSelectedDocuments,   // selectedDocuments
        arbTopicName,           // topicName
        fc.boolean(),           // thinking
        fc.boolean(),           // hasExchanges
        async (connected: boolean, selectedDocuments: Set<string> | undefined, topicName: string | null, thinking: boolean, hasExchanges: boolean) => {
          const hasDocuments = selectedDocuments != null && selectedDocuments.size > 0
          const expectedEnabled = connected && hasDocuments && !!topicName && !thinking && hasExchanges

          // When topicName is null, the component renders a placeholder — no More button at all
          if (topicName === null) {
            // No button to check; skip (the null-topic case is covered by unit tests)
            return
          }

          // To test the thinking state, we need to put the component into thinking mode.
          // We can't directly set thinking=true via props, so we skip thinking=true combos
          // and rely on the unit tests for that case. The property still covers the
          // connected × documents × topic × exchanges dimensions exhaustively.
          if (thinking) {
            return
          }

          const exchanges = hasExchanges ? [sampleExchangeForHistory] : []

          const { unmount } = await act(async () =>
            render(
              <ChatArea
                topicName={topicName}
                connected={connected}
                wsSend={vi.fn()}
                wsOnMessage={vi.fn().mockReturnValue(() => {})}
                onViewTrace={vi.fn()}
                onClearHistory={vi.fn()}
                historyVersion={0}
                selectedDocuments={selectedDocuments}
                loadHistory={vi.fn().mockResolvedValue(exchanges)}
              />
            ),
          )

          const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })

          if (expectedEnabled) {
            expect(moreBtn).not.toBeDisabled()
          } else {
            expect(moreBtn).toBeDisabled()
          }

          unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('ChatArea (shared) - Property 2: Message transmission', () => {
  // Feature: explorer-more-button, Property 2
  // For any valid More button click (enabled state), wsSend is called with
  // { type: 'query', topic: topicName, question: DEEPER_ANALYSIS_PROMPT, document_ids: [...selectedDocuments] }
  // Requirements: 3.1, 4.3

  const arbTopicName = fc.string({ minLength: 1, maxLength: 30 })

  const arbDocumentIds = fc
    .uniqueArray(fc.string({ minLength: 1, maxLength: 12 }), { minLength: 1, maxLength: 8 })
    .map((ids: string[]) => new Set(ids))

  it('wsSend receives correct message structure for any valid topic and document set', async () => {
    const user = userEvent.setup()

    await fc.assert(
      fc.asyncProperty(
        arbTopicName,
        arbDocumentIds,
        async (topicName: string, selectedDocuments: Set<string>) => {
          const wsSend = vi.fn()

          const { unmount } = await act(async () =>
            render(
              <ChatArea
                topicName={topicName}
                connected={true}
                wsSend={wsSend}
                wsOnMessage={vi.fn().mockReturnValue(() => {})}
                onViewTrace={vi.fn()}
                onClearHistory={vi.fn()}
                historyVersion={0}
                selectedDocuments={selectedDocuments}
                loadHistory={vi.fn().mockResolvedValue([sampleExchangeForHistory])}
              />
            ),
          )

          const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
          await user.click(moreBtn)

          expect(wsSend).toHaveBeenCalledTimes(1)
          const sentMsg = wsSend.mock.calls[0][0] as Record<string, unknown>
          expect(sentMsg.type).toBe('query')
          expect(sentMsg.topic).toBe(topicName)
          expect(sentMsg.question).toBe(DEEPER_ANALYSIS_PROMPT)
          // document_ids should contain exactly the same IDs as selectedDocuments
          const sentIds = new Set(sentMsg.document_ids as string[])
          expect(sentIds).toEqual(selectedDocuments)

          unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('ChatArea (shared) - Property 3: Textarea preservation on More click', () => {
  // Feature: explorer-more-button, Property 3
  // For any More button click, the textarea content SHALL be preserved
  // (the More button sends a predefined prompt, not the user's draft).
  // Requirements: 3.3

  const arbTextareaContent = fc.oneof(
    fc.constant(''),
    fc.string({ minLength: 1, maxLength: 50 }),
    fc.constant('   '),
    fc.constant('\t\t'),
    fc.constant('  \t  '),
  )

  it('textarea content is preserved after More click for any initial content', async () => {
    const user = userEvent.setup()

    await fc.assert(
      fc.asyncProperty(
        arbTextareaContent,
        async (content: string) => {
          const { unmount } = await act(async () =>
            render(
              <ChatArea
                topicName="test-topic"
                connected={true}
                wsSend={vi.fn()}
                wsOnMessage={vi.fn().mockReturnValue(() => {})}
                onViewTrace={vi.fn()}
                onClearHistory={vi.fn()}
                historyVersion={0}
                selectedDocuments={new Set(['doc-1'])}
                loadHistory={vi.fn().mockResolvedValue([sampleExchangeForHistory])}
              />
            ),
          )

          const textarea = screen.getByPlaceholderText('Ask a question...') as HTMLTextAreaElement

          // Set textarea content directly (faster than typing for property tests)
          await act(async () => {
            // Use fireEvent to set the value, simulating user input
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
              window.HTMLTextAreaElement.prototype, 'value',
            )!.set!
            nativeInputValueSetter.call(textarea, content)
            textarea.dispatchEvent(new Event('input', { bubbles: true }))
          })

          // Click the More button
          const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
          await user.click(moreBtn)

          // Textarea must preserve its content after More click
          expect(textarea.value).toBe(content)

          unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('ChatArea (shared) - Property 4: Thinking state activation', () => {
  // Feature: explorer-more-button, Property 4
  // For any More button click, the ChatArea SHALL set the thinking state to true,
  // which disables further queries and displays the thinking indicator.
  // Requirements: 3.4

  const arbTopicName = fc.string({ minLength: 1, maxLength: 30 })

  const arbDocumentIds = fc
    .uniqueArray(fc.string({ minLength: 1, maxLength: 12 }), { minLength: 1, maxLength: 8 })
    .map((ids: string[]) => new Set(ids))

  it('thinking indicator appears after More click for any valid state', async () => {
    const user = userEvent.setup()

    await fc.assert(
      fc.asyncProperty(
        arbTopicName,
        arbDocumentIds,
        async (topicName: string, selectedDocuments: Set<string>) => {
          const { unmount } = await act(async () =>
            render(
              <ChatArea
                topicName={topicName}
                connected={true}
                wsSend={vi.fn()}
                wsOnMessage={vi.fn().mockReturnValue(() => {})}
                onViewTrace={vi.fn()}
                onClearHistory={vi.fn()}
                historyVersion={0}
                selectedDocuments={selectedDocuments}
                loadHistory={vi.fn().mockResolvedValue([sampleExchangeForHistory])}
              />
            ),
          )

          // More button should be present before click
          const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
          await user.click(moreBtn)

          // Thinking indicator (3 animated dots) should be visible
          const thinkingDots = document.querySelectorAll('.animate-bounce')
          expect(thinkingDots.length).toBe(3)

          // More button should be hidden while thinking
          expect(screen.queryByRole('button', { name: /deeper analysis/i })).toBeNull()

          unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('ChatArea (shared) - UX consistency after More button click', () => {
  it('displays thinking indicator after More button click', async () => {
    const user = userEvent.setup()
    await renderChatArea()

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // The thinking indicator shows animated dots
    const thinkingDots = document.querySelectorAll('.animate-bounce')
    expect(thinkingDots.length).toBe(3)
  })

  it('displays phase updates from WebSocket status messages after More click', async () => {
    const user = userEvent.setup()
    const { wsOnMessage, dispatch } = createWsOnMessage()
    await renderChatArea({ wsOnMessage })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // Initial phase is 'Starting'
    expect(screen.getByText('Starting')).toBeInTheDocument()

    // Simulate a status update from the server
    await act(async () => {
      dispatch({ type: 'status', phase: 'Analyzing documents', iteration: 1 })
    })

    expect(screen.getByText('Analyzing documents')).toBeInTheDocument()
  })

  it('shows Cancel button during More request processing', async () => {
    const user = userEvent.setup()
    const wsSend = vi.fn()
    await renderChatArea({ wsSend })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // Cancel button should be present and functional
    const cancelBtn = screen.getByRole('button', { name: /cancel/i })
    expect(cancelBtn).toBeInTheDocument()

    await user.click(cancelBtn)
    expect(wsSend).toHaveBeenCalledWith({ type: 'cancel' })
  })

  it('reloads history when More request completes via WebSocket', async () => {
    const user = userEvent.setup()
    const { wsOnMessage, dispatch } = createWsOnMessage()
    const completedExchange = {
      exchange_id: 'ex-more-1',
      question: DEEPER_ANALYSIS_PROMPT,
      answer: 'Here is the deeper analysis...',
      timestamp: '2026-03-16T12:00:00Z',
      tokens: { prompt: 100, completion: 200, total: 300 },
      execution_time: 5.0,
      trace_id: 'trace-1',
      model: 'test-model',
      document_ids: ['doc-1'],
    }
    // loadHistory returns empty initially, then the completed exchange after completion
    const loadHistory = vi.fn()
      .mockResolvedValueOnce([])           // initial load
      .mockResolvedValueOnce([completedExchange]) // reload after complete
    await renderChatArea({ wsOnMessage, loadHistory })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // Simulate completion message from server
    await act(async () => {
      dispatch({
        type: 'complete',
        answer: 'Here is the deeper analysis...',
        trace_id: 'trace-1',
        tokens: { prompt: 100, completion: 200, total: 300 },
        duration_ms: 5000,
      })
    })

    // loadHistory should have been called again to reload the conversation
    // First call: initial mount, Second call: after complete message
    await waitFor(() => {
      expect(loadHistory).toHaveBeenCalledTimes(2)
    })
  })

  it('displays error toast when More request fails via WebSocket', async () => {
    const user = userEvent.setup()
    const { wsOnMessage, dispatch } = createWsOnMessage()
    const mockShowToast = vi.mocked(showToast)
    mockShowToast.mockClear()
    await renderChatArea({ wsOnMessage })

    await user.click(screen.getByRole('button', { name: /deeper analysis/i }))

    // Simulate error message from server
    await act(async () => {
      dispatch({ type: 'error', message: 'Analysis failed: timeout exceeded' })
    })

    expect(mockShowToast).toHaveBeenCalledWith('Analysis failed: timeout exceeded', 'error')
  })
})

describe('ChatArea — allowBackgroundKnowledge', () => {
  it('includes allow_background_knowledge in query message when true', async () => {
    const user = userEvent.setup()
    const props = await renderChatArea({ allowBackgroundKnowledge: true })

    const input = screen.getByRole('textbox')
    await user.type(input, 'Test question')
    await user.keyboard('{Enter}')

    expect(props.wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        allow_background_knowledge: true,
      })
    )
  })

  it('includes allow_background_knowledge=false by default', async () => {
    const user = userEvent.setup()
    const props = await renderChatArea()

    const input = screen.getByRole('textbox')
    await user.type(input, 'Test question')
    await user.keyboard('{Enter}')

    expect(props.wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        allow_background_knowledge: false,
      })
    )
  })

  it('sends allow_background_knowledge with More button', async () => {
    const user = userEvent.setup()
    const props = await renderChatArea({ allowBackgroundKnowledge: true })

    const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
    await user.click(moreBtn)

    expect(props.wsSend).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'query',
        allow_background_knowledge: true,
      })
    )
  })
})

describe('ChatArea — background knowledge hint removed', () => {
  it('does not show hint when checkbox is off and exchanges exist', async () => {
    await renderChatArea({ allowBackgroundKnowledge: false })
    expect(screen.queryByText(/Enable.*background knowledge/i)).not.toBeInTheDocument()
  })

  it('does not show hint when checkbox is on', async () => {
    await renderChatArea({ allowBackgroundKnowledge: true })
    expect(screen.queryByText(/Enable.*background knowledge/i)).not.toBeInTheDocument()
  })
})

// Property 6 (custom onKeyDown handler) was removed because the handler was
// redundant with native <button> Enter/Space activation and caused double-fire.
// Keyboard activation is now tested by the unit tests above via userEvent.

describe('ChatArea (shared) - Property 5: Pending question display', () => {
  // Feature: explorer-more-button, Property 5
  // For any More button click, the ChatArea SHALL set the pendingQuestion state
  // to the deeper analysis prompt text, causing it to be displayed in the chat message area.
  // Requirements: 3.5

  const arbTopicName = fc.string({ minLength: 1, maxLength: 30 })

  const arbDocumentIds = fc
    .uniqueArray(fc.string({ minLength: 1, maxLength: 12 }), { minLength: 1, maxLength: 8 })
    .map((ids: string[]) => new Set(ids))

  it('pendingQuestion equals DEEPER_ANALYSIS_PROMPT after More click for any valid state', async () => {
    const user = userEvent.setup()

    await fc.assert(
      fc.asyncProperty(
        arbTopicName,
        arbDocumentIds,
        async (topicName: string, selectedDocuments: Set<string>) => {
          const { unmount } = await act(async () =>
            render(
              <ChatArea
                topicName={topicName}
                connected={true}
                wsSend={vi.fn()}
                wsOnMessage={vi.fn().mockReturnValue(() => {})}
                onViewTrace={vi.fn()}
                onClearHistory={vi.fn()}
                historyVersion={0}
                selectedDocuments={selectedDocuments}
                loadHistory={vi.fn().mockResolvedValue([sampleExchangeForHistory])}
              />
            ),
          )

          const moreBtn = screen.getByRole('button', { name: /deeper analysis/i })
          await user.click(moreBtn)

          // The pending question should be rendered in the chat area.
          // Multiple elements use bg-accent/10 (loaded exchanges + pending question).
          // The pending question is always the last one rendered.
          const allAccent = document.querySelectorAll('.bg-accent\\/10')
          const pendingEl = allAccent[allAccent.length - 1]
          expect(pendingEl).toBeDefined()
          expect(pendingEl!.textContent).toContain(DEEPER_ANALYSIS_PROMPT)

          unmount()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('ChatArea (shared) - getMorePrompt context-sensitive selection', () => {
  it('returns DEEPER_ANALYSIS_PROMPT when exchanges is empty', () => {
    expect(getMorePrompt([])).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when last exchange has no gave_up flag', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'Here is a detailed analysis of the documents...',
    }]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when last exchange has gave_up=false', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      gave_up: false,
    }]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })

  it('returns RETRY_SEARCH_PROMPT when last exchange has gave_up=true', () => {
    const exchanges = [{
      ...sampleExchangeForHistory,
      answer: 'Found some titles but not enough to answer.',
      gave_up: true,
    }]
    expect(getMorePrompt(exchanges)).toBe(RETRY_SEARCH_PROMPT)
  })

  it('returns DEEPER_ANALYSIS_PROMPT when only earlier exchange had gave_up but last is normal', () => {
    const exchanges = [
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-fail',
        gave_up: true,
      },
      {
        ...sampleExchangeForHistory,
        exchange_id: 'ex-retry',
        answer: 'After retrying, here are the titles in order...',
        gave_up: false,
      },
    ]
    expect(getMorePrompt(exchanges)).toBe(DEEPER_ANALYSIS_PROMPT)
  })
})
