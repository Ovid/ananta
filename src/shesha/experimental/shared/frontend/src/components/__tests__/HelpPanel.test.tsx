import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import HelpPanel from '../HelpPanel'

const defaultProps = {
  onClose: vi.fn(),
  quickStart: [
    'Step one',
    <>Step <strong>two</strong></>,
  ],
  faq: [
    { q: 'Question one?', a: 'Answer one.' },
    { q: 'Question two?', a: <>Answer <strong>two</strong>.</> },
  ],
  shortcuts: [
    { label: 'Send message', key: 'Enter' },
    { label: 'New line', key: 'Shift+Enter' },
  ],
}

describe('HelpPanel', () => {
  it('renders the Help heading', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Help')).toBeInTheDocument()
  })

  it('renders quick start steps as an ordered list', () => {
    render(<HelpPanel {...defaultProps} />)
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Step one')
    expect(items[1]).toHaveTextContent('Step two')
  })

  it('renders HTML in quick start steps', () => {
    render(<HelpPanel {...defaultProps} />)
    const items = screen.getAllByRole('listitem')
    const strong = within(items[1]).getByText('two')
    expect(strong.tagName).toBe('STRONG')
  })

  it('renders FAQ questions and answers', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Question one?')).toBeInTheDocument()
    expect(screen.getByText('Answer one.')).toBeInTheDocument()
    expect(screen.getByText('Question two?')).toBeInTheDocument()
  })

  it('renders HTML in FAQ answers', () => {
    render(<HelpPanel {...defaultProps} />)
    const faqHeading = screen.getByText('FAQ')
    // scope to FAQ section to avoid matching quick start <strong>
    const faqSection = faqHeading.closest('section')!
    const strong = within(faqSection).getByText('two')
    expect(strong.tagName).toBe('STRONG')
  })

  it('renders keyboard shortcuts', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText('Send message')).toBeInTheDocument()
    expect(screen.getByText('Enter')).toBeInTheDocument()
    expect(screen.getByText('New line')).toBeInTheDocument()
    expect(screen.getByText('Shift+Enter')).toBeInTheDocument()
  })

  it('renders the experimental notice with issues link', () => {
    render(<HelpPanel {...defaultProps} />)
    expect(screen.getByText(/experimental software/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'report issues' })
    expect(link).toHaveAttribute('href', 'https://github.com/Ovid/shesha/issues')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(<HelpPanel {...defaultProps} onClose={onClose} />)
    await userEvent.click(screen.getByText('\u00D7'))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
