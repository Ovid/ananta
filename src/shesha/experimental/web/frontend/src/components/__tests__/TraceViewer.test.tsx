import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@shesha/shared-ui', async () => {
  const actual = await vi.importActual<typeof import('@shesha/shared-ui')>('@shesha/shared-ui')
  return { ...actual, showToast: vi.fn() }
})

import { TraceViewer } from '@shesha/shared-ui'

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
})
