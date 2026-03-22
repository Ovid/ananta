import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the api module before importing TopicSidebar
vi.mock('../../api/client', () => ({
  api: {
    topics: {
      list: vi.fn().mockResolvedValue([
        { name: 'chess', document_count: 2, size: '1.0 MB', project_id: 'p1' },
      ]),
      create: vi.fn(),
      rename: vi.fn(),
      delete: vi.fn(),
    },
    papers: {
      list: vi.fn().mockResolvedValue([
        {
          arxiv_id: '2401.00001v1',
          title: 'Chess Strategies',
          authors: ['A. Author'],
          abstract: 'Abstract',
          category: 'cs.AI',
          date: '2024-01-01',
          arxiv_url: 'https://arxiv.org/abs/2401.00001v1',
          source_type: null,
        },
      ]),
    },
  },
}))

import TopicSidebar from '../TopicSidebar'

describe('TopicSidebar paper click selects topic', () => {
  const defaultProps = {
    activeTopic: null as string | null,
    onSelectTopic: vi.fn(),
    onTopicsChange: vi.fn(),
    refreshKey: 0,
    selectedPapers: new Set<string>(),
    onSelectionChange: vi.fn(),
    onPaperClick: vi.fn(),
    onPapersLoaded: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('selects topic when a paper name is clicked', async () => {
    render(<TopicSidebar {...defaultProps} />)

    // Wait for topics to load
    const topicRow = await screen.findByText('chess')
    expect(topicRow).toBeInTheDocument()

    // Expand the topic by clicking the arrow
    const expandBtn = topicRow.closest('div')!.querySelector('button')!
    await userEvent.click(expandBtn)

    // Wait for papers to load and click the paper name
    const paperTitle = await screen.findByText('Chess Strategies')
    await userEvent.click(paperTitle)

    // onSelectTopic should be called with the topic name
    expect(defaultProps.onSelectTopic).toHaveBeenCalledWith('chess')
    // onPaperClick should also be called
    expect(defaultProps.onPaperClick).toHaveBeenCalled()
  })

  it('does not call onSelectTopic when paper clicked in already-active topic', async () => {
    render(<TopicSidebar {...defaultProps} activeTopic="chess" />)

    // Papers auto-load via useEffect when activeTopic matches
    const paperTitle = await screen.findByText('Chess Strategies')
    await userEvent.click(paperTitle)

    // onSelectTopic should NOT be called (topic is already active)
    expect(defaultProps.onSelectTopic).not.toHaveBeenCalled()
    // onPaperClick should still be called
    expect(defaultProps.onPaperClick).toHaveBeenCalled()
  })
})
