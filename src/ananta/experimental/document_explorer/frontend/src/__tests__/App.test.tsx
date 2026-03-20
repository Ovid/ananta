import { render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'

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

const defaultAppState = {
  dark: true,
  toggleTheme: vi.fn(),
  connected: true,
  send: vi.fn(),
  onMessage: vi.fn(() => vi.fn()),
  modelName: 'test-model',
  tokens: { prompt: 0, completion: 0, total: 0 },
  budget: null,
  setBudget: vi.fn(),
  phase: 'Ready',
  setPhase: vi.fn(),
  documentBytes: 0,
  sidebarWidth: 224,
  handleSidebarDrag: vi.fn(),
  activeTopic: null,
  setActiveTopic: vi.fn(),
  handleTopicSelect: vi.fn(),
  traceView: null,
  setTraceView: vi.fn(),
  handleViewTrace: vi.fn(),
  historyVersion: 0,
  setHistoryVersion: vi.fn(),
  setTokens: vi.fn(),
}

vi.mock('@ananta/shared-ui', async () => {
  const actual = await vi.importActual('@ananta/shared-ui')
  return {
    ...actual,
    useAppState: () => ({ ...defaultAppState }),
  }
})

vi.mock('../api/client', () => ({
  api: {
    model: { get: vi.fn().mockResolvedValue({ model: 'test-model' }) },
    documents: {
      list: vi.fn().mockResolvedValue([]),
      listUncategorized: vi.fn().mockResolvedValue([]),
      listForTopic: vi.fn().mockResolvedValue([]),
      get: vi.fn(),
      delete: vi.fn().mockResolvedValue({ status: 'ok' }),
      topics: vi.fn().mockResolvedValue([]),
      upload: vi.fn().mockResolvedValue([]),
    },
    topics: {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
      rename: vi.fn(),
      delete: vi.fn(),
    },
    traces: { list: vi.fn(), get: vi.fn() },
    history: { get: vi.fn().mockResolvedValue({ exchanges: [] }), clear: vi.fn() },
    export: vi.fn().mockResolvedValue('# transcript'),
    contextBudget: vi.fn(),
    topicDocs: { add: vi.fn(), remove: vi.fn() },
  },
}))

// Must import App after mocks are set up
import App from '../App'

/** Flush pending microtasks (resolved promises / state updates) */
async function flush() {
  await act(async () => {
    await new Promise(r => setTimeout(r, 0))
  })
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Header with "Document Explorer"', async () => {
    render(<App />)
    await flush()
    expect(screen.getByText('Document Explorer')).toBeInTheDocument()
  })

  it('renders upload area in sidebar', async () => {
    render(<App />)
    await flush()
    expect(screen.getByRole('button', { name: 'Upload files' })).toBeInTheDocument()
  })

  it('renders StatusBar with Ready phase', async () => {
    render(<App />)
    await flush()
    const footer = document.querySelector('footer')
    expect(footer).toBeInTheDocument()
    expect(within(footer!).getByText('Ready')).toBeInTheDocument()
  })

  it('renders connection lost banner when disconnected', async () => {
    const sharedUi = await import('@ananta/shared-ui')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const spy = vi.spyOn(sharedUi as any, 'useAppState')
    spy.mockReturnValue({
      ...defaultAppState,
      connected: false,
    })

    render(<App />)
    await flush()
    expect(screen.getByText('Connection lost. Reconnecting...')).toBeInTheDocument()

    spy.mockRestore()
  })

  it('renders export transcript button', async () => {
    render(<App />)
    await flush()
    expect(screen.getByLabelText('Export transcript')).toBeInTheDocument()
  })

  it('opens help panel when help button is clicked', async () => {
    render(<App />)
    await flush()
    expect(screen.queryByText('Quick Start')).not.toBeInTheDocument()
    const helpBtn = screen.getByLabelText('Help')
    await userEvent.click(helpBtn)
    expect(screen.getByText('Quick Start')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close help' })).toBeInTheDocument()
  })
})

describe('App - More button integration', () => {
  it('renders More button in ChatArea when topic is active', async () => {
    const sharedUi = await import('@ananta/shared-ui')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const spy = vi.spyOn(sharedUi as any, 'useAppState')
    spy.mockReturnValue({
      ...defaultAppState,
      activeTopic: 'my-topic',
      connected: true,
    })

    render(<App />)
    await flush()

    expect(screen.getByRole('button', { name: /deeper analysis/i })).toBeInTheDocument()

    spy.mockRestore()
  })
})
