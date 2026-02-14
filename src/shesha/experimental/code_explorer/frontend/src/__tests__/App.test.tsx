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

vi.mock('@shesha/shared-ui', async () => {
  const actual = await vi.importActual('@shesha/shared-ui')
  return {
    ...actual,
    useTheme: () => ({ dark: true, toggle: vi.fn() }),
    useWebSocket: () => ({
      connected: true,
      send: vi.fn(),
      onMessage: vi.fn(() => vi.fn()),
    }),
  }
})

vi.mock('../api/client', () => ({
  api: {
    model: { get: vi.fn().mockResolvedValue({ model: 'test-model' }) },
    repos: { list: vi.fn().mockResolvedValue([]), analyze: vi.fn(), getAnalysis: vi.fn(), checkUpdates: vi.fn(), delete: vi.fn() },
    topics: {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
      rename: vi.fn(),
      delete: vi.fn(),
    },
    traces: { list: vi.fn(), get: vi.fn() },
    history: { get: vi.fn().mockResolvedValue({ exchanges: [] }), clear: vi.fn() },
    export: vi.fn(),
    contextBudget: vi.fn(),
    topicRepos: { add: vi.fn(), remove: vi.fn() },
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

  it('renders Header with "Code Explorer"', async () => {
    render(<App />)
    await flush()
    expect(screen.getByText('Code Explorer')).toBeInTheDocument()
  })

  it('renders Add Repo button in sidebar', async () => {
    render(<App />)
    await flush()
    expect(screen.getByTitle('Add repository')).toBeInTheDocument()
  })

  it('shows AddRepoModal when Add Repo is clicked', async () => {
    render(<App />)
    await flush()
    const addBtn = screen.getByTitle('Add repository')
    await userEvent.click(addBtn)
    expect(screen.getByText('Add Repository')).toBeInTheDocument()
  })

  it('renders connection lost banner when disconnected', async () => {
    // Override useWebSocket to return connected=false
    const sharedUi = await import('@shesha/shared-ui')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const useWebSocketSpy = vi.spyOn(sharedUi as any, 'useWebSocket')
    useWebSocketSpy.mockReturnValue({
      connected: false,
      send: vi.fn(),
      onMessage: vi.fn(() => vi.fn()),
    })

    render(<App />)
    await flush()
    expect(screen.getByText('Connection lost. Reconnecting...')).toBeInTheDocument()

    useWebSocketSpy.mockRestore()
  })

  it('renders StatusBar', async () => {
    render(<App />)
    await flush()
    // StatusBar renders a footer with Phase info
    const footer = document.querySelector('footer')
    expect(footer).toBeInTheDocument()
    expect(within(footer!).getByText('Ready')).toBeInTheDocument()
  })
})
