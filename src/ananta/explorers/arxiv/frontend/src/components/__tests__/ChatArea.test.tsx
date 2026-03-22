import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeAll } from 'vitest'

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

// Mock the api module
vi.mock('../../api/client', () => ({
  api: {
    history: { get: vi.fn().mockResolvedValue({ exchanges: [] }) },
  },
}))

// Mock Toast from shared-ui
vi.mock('@ananta/shared-ui', async () => {
  const actual = await vi.importActual<typeof import('@ananta/shared-ui')>('@ananta/shared-ui')
  return { ...actual, showToast: vi.fn() }
})

import ChatArea from '../ChatArea'

describe('ChatArea input disabled state', () => {
  const baseProps = {
    topicName: 'chess',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
  }

  it('disables textarea when no papers are selected', async () => {
    await act(async () => {
      render(<ChatArea {...baseProps} selectedPapers={new Set()} />)
    })
    const textarea = screen.getByPlaceholderText('Select papers in the sidebar first...')
    expect(textarea).toBeDisabled()
  })

  it('enables textarea when papers are selected', async () => {
    await act(async () => {
      render(<ChatArea {...baseProps} selectedPapers={new Set(['paper-1'])} />)
    })
    const textarea = screen.getByPlaceholderText('Ask a question...')
    expect(textarea).not.toBeDisabled()
  })
})

describe('ChatArea state preservation', () => {
  it('preserves thinking indicator and pending question when staying mounted', async () => {
    const user = userEvent.setup()

    const props = {
      topicName: 'chess',
      connected: true,
      wsSend: vi.fn(),
      wsOnMessage: vi.fn().mockReturnValue(() => {}),
      onViewTrace: vi.fn(),
      onClearHistory: vi.fn(),
      historyVersion: 0,
      selectedPapers: new Set(['paper-1']),
      topicPapers: [],
      onPaperClick: vi.fn(),
    }

    let result: ReturnType<typeof render>
    await act(async () => {
      result = render(<ChatArea {...props} />)
    })

    // Type and send a question
    const textarea = screen.getByPlaceholderText('Ask a question...')
    await user.type(textarea, 'What is chess?')
    await user.click(screen.getByText('Send'))

    // Verify thinking state is present
    expect(screen.getByText('What is chess?')).toBeInTheDocument()
    expect(screen.getByText('Starting')).toBeInTheDocument()

    // Re-render with same props (simulates CSS hidden/shown toggle in App.tsx
    // rather than unmount/remount which would destroy state)
    await act(async () => {
      result!.rerender(<ChatArea {...props} />)
    })

    // Thinking state should be preserved — this is why App.tsx uses CSS hidden
    // instead of conditional rendering for the ChatArea/PaperDetail switch
    expect(screen.getByText('What is chess?')).toBeInTheDocument()
    expect(screen.getByText('Starting')).toBeInTheDocument()
  })
})

describe('ChatArea (arXiv) - More button integration', () => {
  it('renders More button when papers are selected', async () => {
    const props = {
      topicName: 'physics',
      connected: true,
      wsSend: vi.fn(),
      wsOnMessage: vi.fn().mockReturnValue(() => {}),
      onViewTrace: vi.fn(),
      onClearHistory: vi.fn(),
      historyVersion: 0,
      selectedPapers: new Set(['2301.00001']),
      topicPapers: [],
      onPaperClick: vi.fn(),
    }

    await act(async () => {
      render(<ChatArea {...props} />)
    })

    expect(screen.getByRole('button', { name: /deeper analysis/i })).toBeInTheDocument()
  })
})
