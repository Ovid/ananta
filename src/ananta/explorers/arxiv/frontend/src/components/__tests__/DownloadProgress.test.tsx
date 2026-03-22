import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DownloadProgress from '../DownloadProgress'

vi.mock('../../api/client', () => ({
  api: {
    papers: {
      taskStatus: vi.fn(),
    },
  },
}))

import { api } from '../../api/client'

const defaultProps = {
  taskIds: ['task-1'],
  onComplete: vi.fn(),
}

describe('DownloadProgress', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('renders a modal with progress bar when downloading', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'downloading' },
        { arxiv_id: '2501.00003', status: 'pending' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    // poll() is called immediately on mount
    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    // Should show progress count: 1 complete out of 3 total
    expect(screen.getByText(/1\/3/)).toBeInTheDocument()
    // Should show currently downloading paper
    expect(screen.getByText(/2501\.00002/)).toBeInTheDocument()
  })

  it('renders nothing when no taskIds', () => {
    render(<DownloadProgress taskIds={[]} onComplete={vi.fn()} />)
    expect(screen.queryByText('Downloading Papers')).not.toBeInTheDocument()
  })

  it('can be dismissed with close button', async () => {
    const user = userEvent.setup()

    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'downloading' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /×/ }))

    expect(screen.queryByText('Downloading Papers')).not.toBeInTheDocument()
  })

  it('calls onComplete when all papers are done', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'complete' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(defaultProps.onComplete).toHaveBeenCalledWith('task-1')
    })
  })

  it('shows animated bar when downloading but none complete', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'downloading' },
        { arxiv_id: '2501.00002', status: 'pending' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    // Progress bar should have animate-progress-slide class, not 0% width
    const barFill = screen.getByTestId('download-bar-fill')
    expect(barFill.className).toContain('animate-progress-slide')
  })

  it('preserves completed task count across polls', async () => {
    vi.useFakeTimers()
    const onComplete = vi.fn()

    // task-1 returns complete, task-2 returns downloading — every poll
    vi.mocked(api.papers.taskStatus).mockImplementation(async (taskId: string) => ({
      task_id: taskId,
      papers: [{
        arxiv_id: taskId === 'task-1' ? '2501.00001' : '2501.00002',
        status: taskId === 'task-1' ? 'complete' : 'downloading',
      }],
    }))

    render(<DownloadProgress taskIds={['task-1', 'task-2']} onComplete={onComplete} />)

    // Flush first poll (called immediately in useEffect)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(screen.getByText(/1\/2/)).toBeInTheDocument()

    // Second poll (2s interval) — task-1 skipped via completedRef
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Without fix: shows 0/1 (completed task papers lost)
    // With fix: still shows 1/2
    expect(screen.getByText(/1\/2/)).toBeInTheDocument()

    vi.useRealTimers()
  })

  it('reappears when a task is replaced at the same length', async () => {
    const user = userEvent.setup()

    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [{ arxiv_id: '2501.00001', status: 'downloading' }],
    })

    const { rerender } = render(
      <DownloadProgress taskIds={['task-1']} onComplete={vi.fn()} />
    )

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    // Dismiss the modal
    await user.click(screen.getByRole('button', { name: /×/ }))
    expect(screen.queryByText('Downloading Papers')).not.toBeInTheDocument()

    // Replace task-1 with task-2 (same array length)
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-2',
      papers: [{ arxiv_id: '2501.00002', status: 'downloading' }],
    })

    rerender(
      <DownloadProgress taskIds={['task-2']} onComplete={vi.fn()} />
    )

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })
  })

  it('shows green bar when all downloads complete', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'complete' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText(/2\/2/)).toBeInTheDocument()
      expect(screen.getByText(/Complete/)).toBeInTheDocument()
    })
  })
})
