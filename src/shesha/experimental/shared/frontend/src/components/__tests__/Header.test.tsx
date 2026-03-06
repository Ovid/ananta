import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import Header from '../Header'

describe('Header (shared)', () => {
  it('renders the app name', () => {
    render(
      <Header appName="Test App" isDark={false} onToggleTheme={() => {}} />
    )
    expect(screen.getByText('Test App')).toBeInTheDocument()
  })

  it('renders Shesha as a link to the GitHub repo', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    const link = screen.getByRole('link', { name: 'Shesha' })
    expect(link).toHaveAttribute('href', 'https://github.com/Ovid/shesha')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('renders Experimental badge', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    expect(screen.getByText('Experimental')).toBeInTheDocument()
  })

  it('renders theme toggle with Light mode label when dark', () => {
    render(
      <Header appName="My App" isDark={true} onToggleTheme={() => {}} />
    )
    const btn = screen.getByRole('button', { name: 'Light mode' })
    expect(btn).toHaveAttribute('data-tooltip', 'Light mode')
  })

  it('renders theme toggle with Dark mode label when light', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    const btn = screen.getByRole('button', { name: 'Dark mode' })
    expect(btn).toHaveAttribute('data-tooltip', 'Dark mode')
  })

  it('calls onToggleTheme when theme button is clicked', async () => {
    const onToggleTheme = vi.fn()
    render(
      <Header appName="My App" isDark={true} onToggleTheme={onToggleTheme} />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Light mode' }))
    expect(onToggleTheme).toHaveBeenCalledOnce()
  })

  it('renders children in the action area', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}}>
        <button>Custom Action</button>
      </Header>
    )
    expect(screen.getByRole('button', { name: 'Custom Action' })).toBeInTheDocument()
  })

  it('renders without children (no app-specific buttons)', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    // Should only have the theme toggle button
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
  })

  it('aligns title text elements by baseline', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    const shesha = screen.getByRole('link', { name: 'Shesha' })
    const titleGroup = shesha.parentElement!
    expect(titleGroup.className).toMatch(/items-baseline/)
  })

  it('does not have title attributes on buttons (to avoid double tooltips)', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}}>
        <button data-tooltip="Test">Child</button>
      </Header>
    )
    const themeBtn = screen.getByRole('button', { name: 'Dark mode' })
    expect(themeBtn).not.toHaveAttribute('title')
  })

  it('renders help button when onHelpToggle is provided', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} onHelpToggle={() => {}} />
    )
    const btn = screen.getByRole('button', { name: 'Help' })
    expect(btn).toHaveAttribute('data-tooltip', 'Help')
  })

  it('does not render help button when onHelpToggle is omitted', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    expect(screen.queryByRole('button', { name: 'Help' })).not.toBeInTheDocument()
  })

  it('calls onHelpToggle when help button is clicked', async () => {
    const onHelpToggle = vi.fn()
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} onHelpToggle={onHelpToggle} />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Help' }))
    expect(onHelpToggle).toHaveBeenCalledOnce()
  })

  it('renders bug report link to GitHub issues', () => {
    render(
      <Header appName="My App" isDark={false} onToggleTheme={() => {}} />
    )
    const link = screen.getByRole('link', { name: 'Report a bug' })
    expect(link).toHaveAttribute('href', 'https://github.com/Ovid/shesha/issues')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveAttribute('data-tooltip', 'Report a bug')
  })
})
