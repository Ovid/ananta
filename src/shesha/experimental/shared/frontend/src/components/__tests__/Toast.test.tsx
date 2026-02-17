import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ToastContainer, { showToast } from '../Toast'

describe('ToastContainer', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when no toasts', () => {
    const { container } = render(<ToastContainer />)
    expect(container.firstChild).toBeNull()
  })

  it('shows a toast via showToast', () => {
    render(<ToastContainer />)
    act(() => {
      showToast('Hello world', 'info')
    })
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('auto-dismisses after 8 seconds', () => {
    render(<ToastContainer />)
    act(() => {
      showToast('Vanish me', 'warning')
    })
    expect(screen.getByText('Vanish me')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(8500)
    })
    expect(screen.queryByText('Vanish me')).not.toBeInTheDocument()
  })

  it('dismisses on close button click', async () => {
    render(<ToastContainer />)
    act(() => {
      showToast('Dismiss me', 'error')
    })
    expect(screen.getByText('Dismiss me')).toBeInTheDocument()

    const closeBtn = screen.getByRole('button')
    await userEvent.click(closeBtn)

    expect(screen.queryByText('Dismiss me')).not.toBeInTheDocument()
  })
})
