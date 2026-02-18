import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AppShell from '../AppShell'

describe('AppShell', () => {
  it('renders children', () => {
    render(
      <AppShell>
        <p>Hello world</p>
      </AppShell>
    )
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('applies h-screen, flex column, and overflow-hidden to the root div', () => {
    render(
      <AppShell>
        <p>Content</p>
      </AppShell>
    )
    const root = screen.getByText('Content').parentElement!
    expect(root.className).toMatch(/h-screen/)
    expect(root.className).toMatch(/flex/)
    expect(root.className).toMatch(/flex-col/)
    expect(root.className).toMatch(/overflow-hidden/)
  })

  it('applies theme classes', () => {
    render(
      <AppShell>
        <p>Themed</p>
      </AppShell>
    )
    const root = screen.getByText('Themed').parentElement!
    expect(root.className).toMatch(/bg-surface-0/)
    expect(root.className).toMatch(/text-text-primary/)
    expect(root.className).toMatch(/font-sans/)
  })

  it('shows connection lost banner when connected is false', () => {
    render(<AppShell connected={false}>Content</AppShell>)
    expect(screen.getByText(/Connection lost/)).toBeTruthy()
  })

  it('hides connection lost banner when connected is true', () => {
    render(<AppShell connected={true}>Content</AppShell>)
    expect(screen.queryByText(/Connection lost/)).toBeNull()
  })

  it('hides connection lost banner by default', () => {
    render(<AppShell>Content</AppShell>)
    expect(screen.queryByText(/Connection lost/)).toBeNull()
  })
})
