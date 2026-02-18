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

    // The citation syntax should NOT appear as literal text in the answer
    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    expect(answerDiv.textContent).not.toContain('[@arxiv:')

    // Instead, there should be an inline citation button inside the answer div
    const inlineButtons = answerDiv.querySelectorAll('button')
    expect(inlineButtons.length).toBe(1)
    expect(inlineButtons[0].textContent).toContain('2005.09008v1')

    fireEvent.click(inlineButtons[0])
    expect(onPaperClick).toHaveBeenCalledWith(basePaper)
  })

  it('renders unknown arxiv ID as plain text', () => {
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

    // Unknown ID should remain as literal citation text
    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    expect(answerDiv.textContent).toContain('[@arxiv:9999.99999v1]')

    // No inline citation button inside the answer div
    const inlineButtons = answerDiv.querySelectorAll('button')
    expect(inlineButtons.length).toBe(0)
  })

  it('renders answer without citations as plain text', () => {
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

    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    expect(answerDiv.textContent).not.toContain('[@arxiv:')

    const inlineButtons = answerDiv.querySelectorAll('button')
    expect(inlineButtons.length).toBe(2)
    expect(inlineButtons[0].textContent).toContain('2005.09008v1')
    expect(inlineButtons[1].textContent).toContain('2401.12345')
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

    // Both IDs should render as clickable buttons despite being in one tag
    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    const inlineButtons = answerDiv.querySelectorAll('button')
    expect(inlineButtons.length).toBe(2)
    expect(inlineButtons[0].textContent).toContain('2005.09008v1')
    expect(inlineButtons[1].textContent).toContain('2401.12345')
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

    const answerDiv = document.querySelector('.whitespace-pre-wrap')!
    const inlineButtons = answerDiv.querySelectorAll('button')
    expect(inlineButtons.length).toBe(1)
    expect(inlineButtons[0].textContent).toContain('astro-ph/0601001v1')
  })
})
