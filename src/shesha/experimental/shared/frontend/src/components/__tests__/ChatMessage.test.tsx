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

  it('does not apply whitespace-pre-wrap even when renderAnswer is provided', () => {
    const customRenderer = (answer: string) => <span>{answer}</span>
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} renderAnswer={customRenderer} />
    )
    expect(document.querySelector('.whitespace-pre-wrap')).toBeNull()
  })

  it('renders answer via markdown when renderAnswer is not provided', () => {
    render(
      <ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />
    )
    // Answer text is present (rendered through markdown)
    expect(screen.getByText('Life arose from chemistry.')).toBeInTheDocument()
    // No citation buttons inside the answer area
    const answerBubble = screen.getByText('Life arose from chemistry.').closest('.bg-surface-2')!
    const buttons = answerBubble.querySelectorAll('button')
    // Only the "View trace" button should exist, not citation buttons
    expect(buttons.length).toBe(1)
    expect(buttons[0].textContent).toBe('View trace')
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
    expect(screen.getByText(/\[@arxiv:2005\.09008v1\]/)).toBeInTheDocument()
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

  it('strips boundary markers from answer before rendering', () => {
    const hex = 'bd0e753b7146bd0089d21bfab2c51ded'
    const exchange = {
      ...baseExchange,
      answer: `Here is the content:\nUNTRUSTED_CONTENT_${hex}_BEGIN\n# Hello World\nUNTRUSTED_CONTENT_${hex}_END`,
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.queryByText(/UNTRUSTED_CONTENT/)).not.toBeInTheDocument()
    expect(screen.getByText('Quoted content')).toBeInTheDocument()
  })

  it('renders markdown in answer by default', () => {
    const exchange = {
      ...baseExchange,
      answer: '## Heading\n\n- item one\n- item two',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Heading')
    expect(screen.getByRole('list')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
  })
})

describe('ChatMessage (shared) - user question markdown', () => {
  it('renders markdown formatting in user questions', () => {
    const exchange = {
      ...baseExchange,
      question: '## My Heading\n\n- item one\n- item two',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveTextContent('My Heading')
    const items = screen.getAllByRole('listitem')
    expect(items.length).toBeGreaterThanOrEqual(2)
  })

  it('renders code blocks in user questions', () => {
    const exchange = {
      ...baseExchange,
      question: 'Check this:\n\n```python\nprint("hello")\n```',
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.getByText('print("hello")')).toBeInTheDocument()
  })

  it('does not apply stripBoundaryMarkers to user questions', () => {
    const hex = 'bd0e753b7146bd0089d21bfab2c51ded'
    const exchange = {
      ...baseExchange,
      question: `UNTRUSTED_CONTENT_${hex}_BEGIN\nsome text\nUNTRUSTED_CONTENT_${hex}_END`,
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    // Boundary markers in questions should NOT be stripped (they only come from assistant)
    expect(screen.queryByText('Quoted content')).not.toBeInTheDocument()
  })
})

describe('ChatMessage — background knowledge rendering', () => {
  it('renders background knowledge section with label and aside role', () => {
    const exchange = {
      ...baseExchange,
      answer: 'Document content.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nInferred content.\n<!-- BACKGROUND_KNOWLEDGE_END -->',
    }
    render(<ChatMessage exchange={exchange} onViewTrace={vi.fn()} />)
    expect(screen.getByText('Document content.')).toBeInTheDocument()
    expect(screen.getByText('Inferred content.')).toBeInTheDocument()
    expect(screen.getByText('Background knowledge')).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toBeInTheDocument()
  })

  it('does not render background label when no markers present', () => {
    render(<ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />)
    expect(screen.queryByText('Background knowledge')).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('skips augmented rendering when renderAnswer prop is provided', () => {
    const exchange = {
      ...baseExchange,
      answer: 'Doc.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nBg.\n<!-- BACKGROUND_KNOWLEDGE_END -->',
    }
    const customRenderer = (answer: string) => <span data-testid="custom">{answer}</span>
    render(<ChatMessage exchange={exchange} onViewTrace={vi.fn()} renderAnswer={customRenderer} />)
    expect(screen.getByTestId('custom')).toBeInTheDocument()
    expect(screen.queryByText('Background knowledge')).not.toBeInTheDocument()
  })
})

describe('ChatMessage — documents-only notice', () => {
  it('shows notice when allow_background_knowledge is true and no markers present', () => {
    const exchange = {
      ...baseExchange,
      allow_background_knowledge: true,
    }
    render(<ChatMessage exchange={exchange} onViewTrace={vi.fn()} />)
    expect(screen.getByText(/Based entirely on your documents/)).toBeInTheDocument()
  })

  it('does not show notice when allow_background_knowledge is false', () => {
    render(<ChatMessage exchange={baseExchange} onViewTrace={vi.fn()} />)
    expect(screen.queryByText(/Based entirely on your documents/)).not.toBeInTheDocument()
  })

  it('does not show notice when background markers are present', () => {
    const exchange = {
      ...baseExchange,
      allow_background_knowledge: true,
      answer: 'Doc.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nBg.\n<!-- BACKGROUND_KNOWLEDGE_END -->',
    }
    render(<ChatMessage exchange={exchange} onViewTrace={vi.fn()} />)
    expect(screen.queryByText(/Based entirely on your documents/)).not.toBeInTheDocument()
  })
})
