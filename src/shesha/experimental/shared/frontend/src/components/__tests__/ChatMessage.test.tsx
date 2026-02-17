import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

import ChatMessage from '../ChatMessage'
import type { Exchange } from '../../types'

const baseExchange: Exchange = {
  exchange_id: 'ex-1',
  question: 'What is abiogenesis?',
  answer: 'Life arose from chemistry.',
  timestamp: '2026-02-13T12:00:00Z',
  tokens: { prompt: 100, completion: 50, total: 150 },
  execution_time: 5.0,
  trace_id: 'trace-1',
  model: 'test-model',
  document_ids: ['doc-1'],
}

describe('ChatMessage (shared)', () => {
  it('renders the question text', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByText('What is abiogenesis?')).toBeInTheDocument()
  })

  it('renders the answer text as plain text by default', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByText('Life arose from chemistry.')).toBeInTheDocument()
  })

  it('renders token count and execution time', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByText('150 tokens')).toBeInTheDocument()
    expect(screen.getByText('5.0s')).toBeInTheDocument()
  })

  it('renders View trace link when trace_id is present', () => {
    const onViewTrace = vi.fn()
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={onViewTrace} />
    )
    expect(screen.getByText('View trace')).toBeInTheDocument()
  })

  it('does not render View trace when trace_id is null', () => {
    const exchange = { ...baseExchange, trace_id: null }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.queryByText('View trace')).not.toBeInTheDocument()
  })

  it('uses renderAnswer prop when provided', () => {
    const customRenderer = (answer: string) => <span data-testid="custom">{answer.toUpperCase()}</span>
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} renderAnswer={customRenderer} />
    )
    expect(screen.getByTestId('custom')).toBeInTheDocument()
    expect(screen.getByText('LIFE AROSE FROM CHEMISTRY.')).toBeInTheDocument()
  })

  it('renders plain text when renderAnswer is not provided', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    expect(answerDiv.textContent).toBe('Life arose from chemistry.')
    // No buttons inside the answer div (no citation rendering by default)
    const buttons = answerDiv.querySelectorAll('button')
    expect(buttons.length).toBe(0)
  })

  it('does not have any arxiv-specific citation parsing', () => {
    const exchange = {
      ...baseExchange,
      answer: 'See [@arxiv:2005.09008v1] for details.',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    // The shared component should NOT parse citations - it renders as-is
    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    expect(answerDiv.textContent).toContain('[@arxiv:2005.09008v1]')
  })

  it('does not render consulted papers section (domain-specific)', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    expect(screen.queryByText('Consulted papers:')).not.toBeInTheDocument()
  })

  it('renders answerFooter when provided', () => {
    render(
      <ChatMessage
        exchange={baseExchange}
        onViewTrace={vi.fn()}
        answerFooter={<div data-testid="footer">Extra info</div>}
      />
    )
    expect(screen.getByTestId('footer')).toBeInTheDocument()
    expect(screen.getByText('Extra info')).toBeInTheDocument()
  })

  it('does not render answerFooter when not provided', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    expect(screen.queryByTestId('footer')).not.toBeInTheDocument()
  })
})
