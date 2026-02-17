import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import AddRepoModal from '../AddRepoModal'

const defaultProps = {
  topics: ['frontend', 'backend', 'infra'],
  onSubmit: vi.fn(),
  onClose: vi.fn(),
}

function renderModal(overrides: Partial<typeof defaultProps> = {}) {
  return render(<AddRepoModal {...defaultProps} {...overrides} />)
}

describe('AddRepoModal', () => {
  it('renders title "Add Repository"', () => {
    renderModal()
    expect(screen.getByText('Add Repository')).toBeInTheDocument()
  })

  it('renders URL input with placeholder', () => {
    renderModal()
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    expect(input).toBeInTheDocument()
  })

  it('renders topic dropdown with "— No topic —" option', () => {
    renderModal()
    const option = screen.getByRole('option', { name: '— No topic —' })
    expect(option).toBeInTheDocument()
  })

  it('renders topic dropdown with provided topics', () => {
    renderModal()
    expect(screen.getByRole('option', { name: 'frontend' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'backend' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'infra' })).toBeInTheDocument()
  })

  it('submit button is disabled when URL is empty', () => {
    renderModal()
    const button = screen.getByRole('button', { name: 'Add' })
    expect(button).toBeDisabled()
  })

  it('submit button is enabled when URL is entered', async () => {
    renderModal()
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    await userEvent.type(input, 'https://github.com/example/repo')
    const button = screen.getByRole('button', { name: 'Add' })
    expect(button).toBeEnabled()
  })

  it('calls onSubmit with URL and no topic when "— No topic —" selected', async () => {
    const onSubmit = vi.fn()
    renderModal({ onSubmit })
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    await userEvent.type(input, 'https://github.com/example/repo')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(onSubmit).toHaveBeenCalledWith('https://github.com/example/repo', undefined)
  })

  it('calls onSubmit with URL and selected topic', async () => {
    const onSubmit = vi.fn()
    renderModal({ onSubmit })
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    await userEvent.type(input, 'https://github.com/example/repo')
    await userEvent.selectOptions(screen.getByRole('combobox'), 'backend')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(onSubmit).toHaveBeenCalledWith('https://github.com/example/repo', 'backend')
  })

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when backdrop is clicked', async () => {
    const onClose = vi.fn()
    const { container } = renderModal({ onClose })
    // Backdrop is the outer fixed div
    const backdrop = container.querySelector('.bg-black\\/50')!
    await userEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('URL input is auto-focused on mount', () => {
    renderModal()
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    expect(input).toHaveFocus()
  })

  it('trims URL whitespace before submitting', async () => {
    const onSubmit = vi.fn()
    renderModal({ onSubmit })
    const input = screen.getByPlaceholderText('https://github.com/owner/repo')
    await userEvent.type(input, '  https://github.com/example/repo  ')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(onSubmit).toHaveBeenCalledWith('https://github.com/example/repo', undefined)
  })

  it('renders with empty topics list', () => {
    renderModal({ topics: [] })
    const select = screen.getByRole('combobox')
    // Only the "— No topic —" option should exist
    const options = select.querySelectorAll('option')
    expect(options).toHaveLength(1)
    expect(options[0].textContent).toBe('— No topic —')
  })
})
