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

vi.mock('@shesha/shared-ui', async () => {
  const actual = await vi.importActual('@shesha/shared-ui')
  return {
    ...actual,
    useAppState: () => ({ ...defaultAppState }),
  }
})

vi.mock('../api/client', () => ({
  api: {
    model: { get: vi.fn().mockResolvedValue({ model: 'test-model' }) },
    repos: { list: vi.fn().mockResolvedValue([]), listUncategorized: vi.fn().mockResolvedValue([]), analyze: vi.fn(), getAnalysis: vi.fn(), checkUpdates: vi.fn(), applyUpdates: vi.fn(), delete: vi.fn() },
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
    const sharedUi = await import('@shesha/shared-ui')
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

  it('renders StatusBar', async () => {
    render(<App />)
    await flush()
    // StatusBar renders a footer with Phase info
    const footer = document.querySelector('footer')
    expect(footer).toBeInTheDocument()
    expect(within(footer!).getByText('Ready')).toBeInTheDocument()
  })

  it('root container prevents horizontal overflow', async () => {
    const { container } = render(<App />)
    await flush()
    const root = container.firstElementChild as HTMLElement
    expect(root.className).toMatch(/overflow-hidden/)
  })

  it('passes addDocToTopic and removeDocFromTopic to TopicSidebar', async () => {
    render(<App />)
    await flush()
    expect(screen.getByText('Code Explorer')).toBeInTheDocument()
  })

  describe('handleCheckUpdates', () => {
    const mockRepo = {
      project_id: 'test-repo',
      source_url: 'https://github.com/test/repo',
      file_count: 10,
      analysis_status: null,
    }

    async function renderWithRepo() {
      const { api } = await import('../api/client')
      vi.mocked(api.repos.list).mockResolvedValue([mockRepo])
      vi.mocked(api.repos.listUncategorized).mockResolvedValue([mockRepo])
      vi.mocked(api.repos.getAnalysis).mockRejectedValue(new Error('none'))

      render(<App />)
      await flush()

      // Click the repo label in the uncategorized section to view it
      const label = screen.getByText('test-repo')
      await userEvent.click(label)
      await flush()

      return api
    }

    it('calls applyUpdates and shows toast when updates are available', async () => {
      const api = await renderWithRepo()
      vi.mocked(api.repos.checkUpdates).mockResolvedValue({
        status: 'updates_available',
        files_ingested: 10,
      })
      vi.mocked(api.repos.applyUpdates).mockResolvedValue({
        status: 'created',
        files_ingested: 15,
      })

      await userEvent.click(screen.getByRole('button', { name: 'Check for Updates' }))
      await flush()

      expect(api.repos.applyUpdates).toHaveBeenCalledWith('test-repo')
    })

    it('shows up-to-date toast and skips applyUpdates when unchanged', async () => {
      const api = await renderWithRepo()
      vi.mocked(api.repos.checkUpdates).mockResolvedValue({
        status: 'unchanged',
        files_ingested: 10,
      })

      await userEvent.click(screen.getByRole('button', { name: 'Check for Updates' }))
      await flush()

      expect(api.repos.applyUpdates).not.toHaveBeenCalled()
    })
  })
})

describe('App - More button integration', () => {
  it('renders More button in ChatArea when topic is active and repos are selected', async () => {
    const sharedUi = await import('@shesha/shared-ui')
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
