import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Markdown from 'react-markdown'

import { preprocessCitations, buildCitationComponents } from '../citations'
import type { PaperInfo } from '../../types'

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

describe('preprocessCitations', () => {
  it('converts [@arxiv:ID] to markdown link', () => {
    expect(preprocessCitations('See [@arxiv:2005.09008v1] for details.'))
      .toBe('See [2005.09008v1](arxiv:2005.09008v1) for details.')
  })

  it('converts multiple citations', () => {
    const input = 'Compare [@arxiv:2005.09008v1] with [@arxiv:2401.12345].'
    const expected = 'Compare [2005.09008v1](arxiv:2005.09008v1) with [2401.12345](arxiv:2401.12345).'
    expect(preprocessCitations(input)).toBe(expected)
  })

  it('handles semicolon-separated IDs in one tag', () => {
    const input = 'See [@arxiv:2005.09008v1; @arxiv:2401.12345] for details.'
    const expected = 'See [2005.09008v1](arxiv:2005.09008v1) [2401.12345](arxiv:2401.12345) for details.'
    expect(preprocessCitations(input)).toBe(expected)
  })

  it('handles old-style arxiv IDs with slashes', () => {
    expect(preprocessCitations('See [@arxiv:astro-ph/0601001v1] for details.'))
      .toBe('See [astro-ph/0601001v1](arxiv:astro-ph/0601001v1) for details.')
  })

  it('preserves unknown citation patterns as literal text', () => {
    expect(preprocessCitations('See [@arxiv:not-valid] for details.'))
      .toBe('See [@arxiv:not-valid] for details.')
  })

  it('returns text unchanged when no citations present', () => {
    expect(preprocessCitations('No citations here.'))
      .toBe('No citations here.')
  })
})

describe('buildCitationComponents', () => {
  it('renders arxiv: links as citation buttons', () => {
    const onPaperClick = vi.fn()
    const components = buildCitationComponents([basePaper], onPaperClick)

    render(
      <Markdown components={components} urlTransform={(url) => url.startsWith('arxiv:') ? url : url}>
        {'[2005.09008v1](arxiv:2005.09008v1)'}
      </Markdown>
    )

    const button = screen.getByRole('button', { name: '2005.09008v1' })
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('title', 'An Objective Bayesian Analysis')

    fireEvent.click(button)
    expect(onPaperClick).toHaveBeenCalledWith(basePaper)
  })

  it('renders unknown arxiv: IDs as plain text', () => {
    const components = buildCitationComponents([basePaper], vi.fn())

    render(
      <Markdown components={components} urlTransform={(url) => url.startsWith('arxiv:') ? url : url}>
        {'[9999.99999v1](arxiv:9999.99999v1)'}
      </Markdown>
    )

    // Should render as plain text, not a button
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('9999.99999v1')).toBeInTheDocument()
  })

  it('renders non-arxiv links as normal links', () => {
    const components = buildCitationComponents([], vi.fn())

    render(
      <Markdown components={components} urlTransform={(url) => url.startsWith('arxiv:') ? url : url}>
        {'[Example](https://example.com)'}
      </Markdown>
    )

    const link = screen.getByRole('link', { name: 'Example' })
    expect(link).toHaveAttribute('href', 'https://example.com')
  })

  it('includes mdComponents styling (headings, lists, etc.)', () => {
    const components = buildCitationComponents([], vi.fn())

    render(
      <Markdown components={components} urlTransform={(url) => url.startsWith('arxiv:') ? url : url}>
        {'## Heading\n\n- item one'}
      </Markdown>
    )

    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Heading')
    expect(screen.getByRole('list')).toBeInTheDocument()
  })

  it('works without topicPapers (renders all arxiv links as plain text)', () => {
    const components = buildCitationComponents(undefined, vi.fn())

    render(
      <Markdown components={components} urlTransform={(url) => url.startsWith('arxiv:') ? url : url}>
        {'[2005.09008v1](arxiv:2005.09008v1)'}
      </Markdown>
    )

    // No matching paper, so rendered as plain text
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('2005.09008v1')).toBeInTheDocument()
  })
})
