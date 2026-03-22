import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SearchPanel from '../SearchPanel'

// Mock the api module
vi.mock('../../api/client', () => ({
  api: {
    papers: {
      add: vi.fn(),
    },
    search: vi.fn(),
  },
}))

// Mock Toast to capture calls
vi.mock('@ananta/shared-ui', async () => {
  const actual = await vi.importActual<typeof import('@ananta/shared-ui')>('@ananta/shared-ui')
  return { ...actual, showToast: vi.fn() }
})

import { api } from '../../api/client'
import { showToast } from '@ananta/shared-ui'

const makeResult = (id: string, title: string, inTopics: string[] = []) => ({
  arxiv_id: id,
  title,
  authors: ['Author'],
  abstract: 'Abstract',
  category: 'cs.AI',
  date: '2025-01-01',
  arxiv_url: `https://arxiv.org/abs/${id}`,
  in_topics: inTopics,
})

const defaultProps = {
  activeTopic: 'my-topic',
  onClose: vi.fn(),
  onPapersChanged: vi.fn(),
  onDownloadStarted: vi.fn(),
}

/** Search and wait for results to appear. */
async function searchAndWait(user: ReturnType<typeof userEvent.setup>, query: string) {
  const input = screen.getByPlaceholderText('Search arXiv...')
  await user.type(input, query)
  await user.click(screen.getByRole('button', { name: 'Go' }))
}

describe('SearchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('addSelected passes task_id to onDownloadStarted', () => {
    it('calls onDownloadStarted when api returns a task_id', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([makeResult('2501.00001', 'Test Paper')])
      vi.mocked(api.papers.add).mockResolvedValue({ task_id: 'task-abc-123' })

      render(<SearchPanel {...defaultProps} />)

      await searchAndWait(user, 'test query')

      await waitFor(() => {
        expect(screen.getByText('Test Paper')).toBeInTheDocument()
      })

      // Select the paper via checkbox
      await user.click(screen.getByRole('checkbox'))

      await user.click(screen.getByRole('button', { name: /Add 1 paper/ }))

      await waitFor(() => {
        expect(defaultProps.onDownloadStarted).toHaveBeenCalledWith('task-abc-123')
      })
    })

    it('does not call onDownloadStarted when api returns no task_id', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([makeResult('2501.00002', 'Cached Paper')])
      vi.mocked(api.papers.add).mockResolvedValue({})

      render(<SearchPanel {...defaultProps} />)

      await searchAndWait(user, 'cached')

      await waitFor(() => {
        expect(screen.getByText('Cached Paper')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('checkbox'))
      await user.click(screen.getByRole('button', { name: /Add 1 paper/ }))

      await waitFor(() => {
        expect(api.papers.add).toHaveBeenCalled()
      })

      expect(defaultProps.onDownloadStarted).not.toHaveBeenCalled()
    })
  })

  describe('checkboxes', () => {
    it('renders a checkbox for each search result', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
      ])

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(2)
      expect(checkboxes[0]).not.toBeChecked()
      expect(checkboxes[1]).not.toBeChecked()
    })

    it('toggles checkbox when clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([makeResult('2501.00001', 'Paper A')])

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(checkbox).toBeChecked()

      await user.click(checkbox)
      expect(checkbox).not.toBeChecked()
    })
  })

  describe('All / None selection', () => {
    it('selects all results when "All" is clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
        makeResult('2501.00003', 'Paper C'),
      ])

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'All' }))

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(3)
      checkboxes.forEach(cb => expect(cb).toBeChecked())
      expect(screen.getByText('3 selected')).toBeInTheDocument()
    })

    it('deselects all results when "None" is clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
      ])

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      // Select all first
      await user.click(screen.getByRole('button', { name: 'All' }))
      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach(cb => expect(cb).toBeChecked())

      // Now deselect all
      await user.click(screen.getByRole('button', { name: 'None' }))
      checkboxes.forEach(cb => expect(cb).not.toBeChecked())
    })

    it('does not show All/None when there are no results', () => {
      render(<SearchPanel {...defaultProps} />)

      expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'None' })).not.toBeInTheDocument()
    })
  })

  describe('progress bar during add', () => {
    it('shows progress bar while adding papers', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
      ])

      // Make add slow enough to observe progress
      let resolveFirst!: (v: { task_id?: string }) => void
      let resolveSecond!: (v: { task_id?: string }) => void
      vi.mocked(api.papers.add)
        .mockImplementationOnce(() => new Promise(r => { resolveFirst = r }))
        .mockImplementationOnce(() => new Promise(r => { resolveSecond = r }))

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      // Select all
      await user.click(screen.getByRole('button', { name: 'All' }))

      // Click add
      await user.click(screen.getByRole('button', { name: /Add 2 papers/ }))

      // Progress bar should appear
      await waitFor(() => {
        expect(screen.getByText('Adding papers...')).toBeInTheDocument()
        expect(screen.getByText('0/2')).toBeInTheDocument()
      })

      // Resolve first paper
      resolveFirst({})
      await waitFor(() => {
        expect(screen.getByText('1/2')).toBeInTheDocument()
      })

      // Resolve second paper
      resolveSecond({})
      await waitFor(() => {
        expect(screen.queryByText('Adding papers...')).not.toBeInTheDocument()
      })
    })

    it('updates in_topics tags after adding', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
      ])
      vi.mocked(api.papers.add).mockResolvedValue({})

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      // No topic tag yet
      expect(screen.queryByText('my-topic')).not.toBeInTheDocument()

      await user.click(screen.getByRole('checkbox'))
      await user.click(screen.getByRole('button', { name: /Add 1 paper/ }))

      // After adding, the topic tag should appear on the result card
      await waitFor(() => {
        expect(screen.getByText('my-topic')).toBeInTheDocument()
      })
    })

    it('shows completion state instead of toast after adding', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
      ])
      vi.mocked(api.papers.add).mockResolvedValue({})

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'All' }))
      await user.click(screen.getByRole('button', { name: /Add 2 papers/ }))

      // Should show completion message in progress bar area, NOT a success toast
      await waitFor(() => {
        expect(screen.getByText('Added 2 papers')).toBeInTheDocument()
      })

      // No success toast should have been shown
      const toastCalls = vi.mocked(showToast).mock.calls
      const successCalls = toastCalls.filter(([, type]) => type === 'success')
      expect(successCalls).toHaveLength(0)
    })
  })

  describe('empty results', () => {
    it('shows "No results found" when search returns empty', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([])

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'barsoom')

      await waitFor(() => {
        expect(screen.getByText(/no results found/i)).toBeInTheDocument()
      })
    })
  })

  describe('add errors', () => {
    it('shows error toast when add fails and continues with remaining papers', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        makeResult('2501.00001', 'Paper A'),
        makeResult('2501.00002', 'Paper B'),
      ])
      vi.mocked(api.papers.add)
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({})

      render(<SearchPanel {...defaultProps} />)
      await searchAndWait(user, 'test')

      await waitFor(() => {
        expect(screen.getByText('Paper A')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'All' }))
      await user.click(screen.getByRole('button', { name: /Add 2 papers/ }))

      await waitFor(() => {
        expect(vi.mocked(showToast)).toHaveBeenCalledWith('Network error', 'error')
      })

      // Should still complete and call onPapersChanged
      await waitFor(() => {
        expect(defaultProps.onPapersChanged).toHaveBeenCalled()
      })
    })
  })
})
