import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'

vi.mock('../Toast', () => ({
  showToast: vi.fn(),
  default: () => null,
}))

import TraceViewer from '../TraceViewer'

const mockTrace = {
  trace_id: 't-1',
  question: 'A '.repeat(500),
  model: 'test-model',
  status: 'success',
  timestamp: '2025-01-01T00:00:00Z',
  total_iterations: 3,
  duration_ms: 5000,
  total_tokens: { prompt: 100, completion: 50 },
  document_ids: [],
  steps: [
    { step_type: 'code_generated', iteration: 1, content: 'print("hi")', tokens_used: 10, timestamp: '2025-01-01T00:00:01Z' },
  ],
}

describe('TraceViewer scrollability', () => {
  it('wraps trace content in a scrollable container', async () => {
    const fetchTrace = vi.fn().mockResolvedValue(mockTrace)

    await act(async () => {
      render(<TraceViewer topicName="test" traceId="t-1" onClose={vi.fn()} fetchTrace={fetchTrace} />)
    })

    // Wait for trace to load
    await screen.findByText(/test-model/)

    // The panel should have a scrollable content area wrapping summary + steps
    const panel = document.querySelector('.fixed.inset-y-0')!
    const scrollable = panel.querySelector('.overflow-y-auto')
    expect(scrollable).toBeTruthy()

    // The scrollable area must contain both the summary and the steps
    expect(scrollable!.textContent).toContain('test-model')
    expect(scrollable!.textContent).toContain('code_generated')
  })

  it('calls fetchTrace with topicName and traceId', async () => {
    const fetchTrace = vi.fn().mockResolvedValue(mockTrace)

    await act(async () => {
      render(<TraceViewer topicName="my-topic" traceId="t-42" onClose={vi.fn()} fetchTrace={fetchTrace} />)
    })

    expect(fetchTrace).toHaveBeenCalledWith('my-topic', 't-42')
  })
})

describe('TraceViewer markdown rendering', () => {
  it('renders final_answer step content as markdown', async () => {
    const user = userEvent.setup()
    const traceWithMarkdown = {
      ...mockTrace,
      steps: [
        {
          step_type: 'final_answer',
          iteration: 1,
          content: '# Main Heading\n\nSome **bold** text and a list:\n\n- item one\n- item two',
          tokens_used: 20,
          timestamp: '2025-01-01T00:00:02Z',
        },
      ],
    }
    const fetchTrace = vi.fn().mockResolvedValue(traceWithMarkdown)

    await act(async () => {
      render(<TraceViewer topicName="test" traceId="t-1" onClose={vi.fn()} fetchTrace={fetchTrace} />)
    })

    await screen.findByText(/test-model/)

    // Expand the step
    await user.click(screen.getByText('final_answer'))

    // Markdown should produce an <h1> and <strong> element
    const stepContent = document.querySelector('[data-testid="step-content-0"]')!
    expect(stepContent.querySelector('h1')).toBeTruthy()
    expect(stepContent.querySelector('strong')).toBeTruthy()
    expect(stepContent.querySelector('li')).toBeTruthy()
  })

  it('renders code_generated step content as plain monospace text', async () => {
    const user = userEvent.setup()
    const traceWithCode = {
      ...mockTrace,
      steps: [
        {
          step_type: 'code_generated',
          iteration: 1,
          content: '# this is a comment\nprint("hello")',
          tokens_used: 10,
          timestamp: '2025-01-01T00:00:01Z',
        },
      ],
    }
    const fetchTrace = vi.fn().mockResolvedValue(traceWithCode)

    await act(async () => {
      render(<TraceViewer topicName="test" traceId="t-1" onClose={vi.fn()} fetchTrace={fetchTrace} />)
    })

    await screen.findByText(/test-model/)

    // Expand the step
    await user.click(screen.getByText('code_generated'))

    // code_generated should NOT render markdown - # should not become <h1>
    const stepContent = document.querySelector('[data-testid="step-content-0"]')!
    expect(stepContent.querySelector('h1')).toBeFalsy()
    expect(stepContent.textContent).toContain('# this is a comment')
  })
})
