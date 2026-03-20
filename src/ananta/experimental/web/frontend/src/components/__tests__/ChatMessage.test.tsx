import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

import ChatMessage from '../ChatMessage'
import type { Exchange, PaperInfo } from '../../types'

const basePaper: PaperInfo = {
  arxiv_id: '2005.09008v1',
  title: 'An Objective Bayesian Analysis',
  authors: ['David Kipping'],
  abstract: 'Life emerged...',
  category: 'astro-ph.EP',
  date: '2020-05-18',
  arxiv_url: 'https://arxiv.org/abs/2005.09008v1',
  source_type: 'latex',
}

const baseExchange: Exchange = {
  exchange_id: 'ex-1',
  question: 'What is abiogenesis?',
  answer: 'See [@arxiv:2005.09008v1] for details.',
  timestamp: '2026-02-13T12:00:00Z',
  tokens: { prompt: 100, completion: 50, total: 150 },
  execution_time: 5.0,
  trace_id: 'trace-1',
  model: 'test-model',
  document_ids: ['2005.09008v1'],
}

/** Helper: find the assistant answer bubble (the .bg-surface-2 div). */
function getAnswerBubble(): HTMLElement {
  return document.querySelector('.bg-surface-2')!
}

/** Helper: find inline citation buttons (have mx-0.5 class from buildCitationComponents). */
function getInlineCitationButtons(): HTMLButtonElement[] {
  const answerBubble = getAnswerBubble()
  const buttons = answerBubble.querySelectorAll('button')
  return Array.from(buttons).filter(b => b.classList.contains('mx-0.5')) as HTMLButtonElement[]
}

describe('ChatMessage citation rendering', () => {
  it('renders [@arxiv:ID] as a clickable button and removes the citation syntax', () => {
    const onPaperClick = vi.fn()
    render(
      <ChatMessage
        exchange={baseExchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={onPaperClick}
      />
    )

    const answerBubble = getAnswerBubble()
    // The citation syntax should NOT appear as literal text
    expect(answerBubble.textContent).not.toContain('[@arxiv:')

    // There should be exactly one inline citation button
    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(1)
    expect(citationButtons[0].textContent).toContain('2005.09008v1')

    fireEvent.click(citationButtons[0])
    expect(onPaperClick).toHaveBeenCalledWith(basePaper)
  })

  it('renders unknown arxiv ID as plain text (not a button)', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'See [@arxiv:9999.99999v1] for details.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={vi.fn()}
      />
    )

    const answerBubble = getAnswerBubble()
    // Unknown ID renders as plain text (ID without citation syntax)
    expect(answerBubble.textContent).toContain('9999.99999v1')

    // No inline citation buttons
    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(0)
  })

  it('renders answer without citations as text', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'No citations here.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={vi.fn()}
      />
    )

    expect(screen.getByText('No citations here.')).toBeDefined()
  })

  it('renders multiple citations in one answer', () => {
    const paper2: PaperInfo = {
      ...basePaper,
      arxiv_id: '2401.12345',
      title: 'Another Paper',
    }
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'Compare [@arxiv:2005.09008v1] with [@arxiv:2401.12345].',
      document_ids: ['2005.09008v1', '2401.12345'],
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper, paper2]}
        onPaperClick={vi.fn()}
      />
    )

    const answerBubble = getAnswerBubble()
    expect(answerBubble.textContent).not.toContain('[@arxiv:')

    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(2)
    expect(citationButtons[0].textContent).toContain('2005.09008v1')
    expect(citationButtons[1].textContent).toContain('2401.12345')
  })

  it('renders semicolon-separated citations as individual clickable buttons', () => {
    const paper2: PaperInfo = {
      ...basePaper,
      arxiv_id: '2401.12345',
      title: 'Another Paper',
    }
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'See [@arxiv:2005.09008v1; @arxiv:2401.12345] for details.',
      document_ids: ['2005.09008v1', '2401.12345'],
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper, paper2]}
        onPaperClick={vi.fn()}
      />
    )

    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(2)
    expect(citationButtons[0].textContent).toContain('2005.09008v1')
    expect(citationButtons[1].textContent).toContain('2401.12345')
  })

  it('renders old-style arxiv IDs with slashes as clickable buttons', () => {
    const oldPaper: PaperInfo = {
      ...basePaper,
      arxiv_id: 'astro-ph/0601001v1',
      title: 'Old Style Paper',
    }
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'See [@arxiv:astro-ph/0601001v1] for details.',
      document_ids: ['astro-ph/0601001v1'],
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[oldPaper]}
        onPaperClick={vi.fn()}
      />
    )

    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(1)
    expect(citationButtons[0].textContent).toContain('astro-ph/0601001v1')
  })
})

describe('ChatMessage markdown rendering', () => {
  it('renders headings in the answer', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: '## Key Findings\n\nSome text here.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[]}
        onPaperClick={vi.fn()}
      />
    )

    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Key Findings')
  })

  it('renders bullet lists in the answer', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: '- item one\n- item two\n- item three',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[]}
        onPaperClick={vi.fn()}
      />
    )

    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('renders bold text in the answer', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'This is **important** text.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[]}
        onPaperClick={vi.fn()}
      />
    )

    const strong = document.querySelector('strong')
    expect(strong).not.toBeNull()
    expect(strong!.textContent).toBe('important')
  })

  it('renders markdown alongside citations', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: '## Summary\n\nKey finding from [@arxiv:2005.09008v1]:\n\n- Point one\n- Point two',
      document_ids: ['2005.09008v1'],
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={vi.fn()}
      />
    )

    // Markdown renders
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Summary')
    expect(screen.getByRole('list')).toBeInTheDocument()

    // Citation renders as button
    const citationButtons = getInlineCitationButtons()
    expect(citationButtons.length).toBe(1)
    expect(citationButtons[0].textContent).toContain('2005.09008v1')
  })
})
