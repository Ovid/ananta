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
    repos: { list: vi.fn().mockResolvedValue([]), listUncategorized: vi.fn().mockResolvedValue([]), get: vi.fn(), analyze: vi.fn(), getAnalysis: vi.fn(), checkUpdates: vi.fn(), applyUpdates: vi.fn(), delete: vi.fn() },
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
import type { Exchange } from '../types'

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
      display_name: null,
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

  describe('handleAnalyze', () => {
    const mockRepo = {
      project_id: 'test-repo',
      source_url: 'https://github.com/test/repo',
      file_count: 10,
      analysis_status: 'missing' as const,
      display_name: null,
    }

    const sampleAnalysis = {
      version: '1',
      generated_at: '2026-05-05T10:00:00Z',
      head_sha: 'abc123',
      overview: 'Sample overview text.',
      components: [],
      external_dependencies: [],
      caveats: '',
    }

    async function renderWithRepoSelected() {
      const { api } = await import('../api/client')
      vi.mocked(api.repos.list).mockResolvedValue([mockRepo])
      vi.mocked(api.repos.listUncategorized).mockResolvedValue([mockRepo])
      vi.mocked(api.repos.getAnalysis).mockRejectedValue(new Error('none'))

      render(<App />)
      await flush()

      const label = screen.getByText('test-repo')
      await userEvent.click(label)
      await flush()

      return api
    }

    it('keeps "Analyzing…" state visible after closing and reopening the detail panel', async () => {
      const api = await renderWithRepoSelected()
      // Make analyze hang so we can verify state is preserved across navigation
      let resolveAnalyze!: (v: typeof sampleAnalysis) => void
      vi.mocked(api.repos.analyze).mockImplementation(
        () => new Promise(r => { resolveAnalyze = r }),
      )

      await userEvent.click(screen.getByRole('button', { name: 'Generate Analysis' }))
      await flush()
      // Buttons are hidden, "Analysis in progress" is shown
      expect(screen.getByText(/analysis in progress/i)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Generate Analysis' })).not.toBeInTheDocument()

      // Close detail
      await userEvent.click(screen.getByRole('button', { name: /close/i }))
      await flush()
      expect(screen.queryByText(/analysis in progress/i)).not.toBeInTheDocument()

      // Reopen detail by clicking the repo again
      await userEvent.click(screen.getByText('test-repo'))
      await flush()

      // Should still show "Analysis in progress" — and no Generate button
      expect(screen.getByText(/analysis in progress/i)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Generate Analysis' })).not.toBeInTheDocument()

      // Resolve the analyze promise to clean up
      await act(async () => {
        resolveAnalyze(sampleAnalysis)
      })
    })

    it('refreshes repo info after analyze completes so the badge reflects new status', async () => {
      const api = await renderWithRepoSelected()
      vi.mocked(api.repos.analyze).mockResolvedValue(sampleAnalysis)
      // After analyze completes, the refreshed RepoInfo should report "current"
      vi.mocked(api.repos.get).mockResolvedValue({
        ...mockRepo,
        analysis_status: 'current',
      })

      // Sanity: badge starts as "not analyzed"
      expect(screen.getByText('not analyzed')).toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: 'Generate Analysis' }))
      await flush()

      // Badge should now reflect "current" (not "not analyzed")
      expect(screen.queryByText('not analyzed')).not.toBeInTheDocument()
      expect(screen.getByText('current')).toBeInTheDocument()
    })

    it('does not start a second analyze when the user clicks Generate Analysis twice', async () => {
      const api = await renderWithRepoSelected()
      let resolveAnalyze!: (v: typeof sampleAnalysis) => void
      vi.mocked(api.repos.analyze).mockImplementation(
        () => new Promise(r => { resolveAnalyze = r }),
      )

      await userEvent.click(screen.getByRole('button', { name: 'Generate Analysis' }))
      await flush()
      expect(api.repos.analyze).toHaveBeenCalledTimes(1)

      // Close and reopen
      await userEvent.click(screen.getByRole('button', { name: /close/i }))
      await flush()
      await userEvent.click(screen.getByText('test-repo'))
      await flush()

      // The Generate button is hidden during analysis; only "Analysis in progress" is visible.
      expect(screen.queryByRole('button', { name: 'Generate Analysis' })).not.toBeInTheDocument()
      expect(screen.getByText(/analysis in progress/i)).toBeInTheDocument()

      // Clean up
      await act(async () => {
        resolveAnalyze(sampleAnalysis)
      })
    })
  })
})

describe('App - renderAnswerFooter (consulted repositories)', () => {
  const mockRepos = [
    { project_id: 'repo-1', source_url: 'https://github.com/a/one', file_count: 5, analysis_status: null, display_name: 'Alpha Repo' },
    { project_id: 'repo-2', source_url: 'https://github.com/b/two', file_count: 3, analysis_status: null, display_name: null },
  ]

  async function renderWithHistory(exchanges: Exchange[]) {
    const { api } = await import('../api/client')
    vi.mocked(api.repos.list).mockResolvedValue(mockRepos)
    vi.mocked(api.repos.listUncategorized).mockResolvedValue([])
    vi.mocked(api.history.get).mockResolvedValue({ exchanges })

    const sharedUi = await import('@ananta/shared-ui')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const spy = vi.spyOn(sharedUi as any, 'useAppState')
    spy.mockReturnValue({ ...defaultAppState, activeTopic: 'test-topic', connected: true })

    render(<App />)
    await flush()
    return spy
  }

  it('shows "Repositories:" label with display names for consulted repos', async () => {
    const spy = await renderWithHistory([
      {
        exchange_id: 'ex-1',
        question: 'What does this do?',
        answer: 'It does X.',
        trace_id: null,
        timestamp: '2026-03-20T10:00:00Z',
        execution_time: 5,
        tokens: { prompt: 100, completion: 50, total: 150 },
        model: 'test-model',
        document_ids: ['repo-1', 'repo-2'],
      },
    ])

    expect(screen.getByText('Repositories:')).toBeInTheDocument()
    expect(screen.getByText('Alpha Repo')).toBeInTheDocument()
    // repo-2 has no display_name, should fall back to project_id
    expect(screen.getByText('repo-2')).toBeInTheDocument()

    spy.mockRestore()
  })

  it('does not render footer when document_ids is empty', async () => {
    const spy = await renderWithHistory([
      {
        exchange_id: 'ex-2',
        question: 'Hello',
        answer: 'Hi.',
        trace_id: null,
        timestamp: '2026-03-20T10:00:00Z',
        execution_time: 1,
        tokens: { prompt: 10, completion: 5, total: 15 },
        model: 'test-model',
        document_ids: [],
      },
    ])

    expect(screen.queryByText('Repositories:')).not.toBeInTheDocument()

    spy.mockRestore()
  })

  it('clicking a repo badge opens the repo detail panel', async () => {
    const { api } = await import('../api/client')
    vi.mocked(api.repos.getAnalysis).mockRejectedValue(new Error('none'))

    const spy = await renderWithHistory([
      {
        exchange_id: 'ex-3',
        question: 'Explain',
        answer: 'Sure.',
        trace_id: null,
        timestamp: '2026-03-20T10:00:00Z',
        execution_time: 2,
        tokens: { prompt: 50, completion: 25, total: 75 },
        model: 'test-model',
        document_ids: ['repo-1'],
      },
    ])

    await userEvent.click(screen.getByText('Alpha Repo'))
    await flush()

    // RepoDetail panel should now be visible with the repo's source URL
    expect(screen.getByText('https://github.com/a/one')).toBeInTheDocument()

    spy.mockRestore()
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
