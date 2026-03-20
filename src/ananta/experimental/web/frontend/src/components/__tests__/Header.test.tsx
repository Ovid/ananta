import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Header from '../Header'

const defaultProps = {
  onSearchToggle: vi.fn(),
  onCheckCitations: vi.fn(),
  onExport: vi.fn(),
  onHelpToggle: vi.fn(),
  dark: true,
  onThemeToggle: vi.fn(),
}

describe('Header', () => {
  it('renders Shesha as a link to the GitHub repo in a new tab', () => {
    render(<Header {...defaultProps} />)
    const link = screen.getByRole('link', { name: 'Shesha' })
    expect(link).toHaveAttribute('href', 'https://github.com/Ovid/shesha')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  describe('toolbar tooltips', () => {
    it('renders tooltip for search button', () => {
      render(<Header {...defaultProps} />)
      const btn = screen.getByRole('button', { name: 'Search arXiv' })
      expect(btn).toHaveAttribute('data-tooltip', 'Search arXiv')
    })

    it('renders tooltip for check citations button', () => {
      render(<Header {...defaultProps} />)
      const btn = screen.getByRole('button', { name: 'Check citations' })
      expect(btn).toHaveAttribute('data-tooltip', 'Check citations')
    })

    it('renders tooltip for export button', () => {
      render(<Header {...defaultProps} />)
      const btn = screen.getByRole('button', { name: 'Export transcript' })
      expect(btn).toHaveAttribute('data-tooltip', 'Export transcript')
    })

    it('renders tooltip for help button', () => {
      render(<Header {...defaultProps} />)
      const btn = screen.getByRole('button', { name: 'Help' })
      expect(btn).toHaveAttribute('data-tooltip', 'Help')
    })

    it('renders tooltip for dark mode toggle', () => {
      render(<Header {...defaultProps} dark={true} />)
      const btn = screen.getByRole('button', { name: 'Light mode' })
      expect(btn).toHaveAttribute('data-tooltip', 'Light mode')
    })

    it('renders tooltip for light mode toggle', () => {
      render(<Header {...defaultProps} dark={false} />)
      const btn = screen.getByRole('button', { name: 'Dark mode' })
      expect(btn).toHaveAttribute('data-tooltip', 'Dark mode')
    })

    it('does not have title attributes (to avoid double tooltips)', () => {
      render(<Header {...defaultProps} />)
      const buttons = screen.getAllByRole('button')
      for (const btn of buttons) {
        expect(btn).not.toHaveAttribute('title')
      }
    })
  })
})
