import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import ConfirmDialog from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title and message', () => {
    render(
      <ConfirmDialog
        title="Delete item"
        message="Are you sure you want to delete this?"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Delete item')).toBeInTheDocument()
    expect(screen.getByText('Are you sure you want to delete this?')).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button is clicked', async () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        title="Test"
        message="Confirm?"
        confirmLabel="Yes"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    )
    await userEvent.click(screen.getByText('Yes'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Test"
        message="Cancel?"
        cancelLabel="No"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    )
    await userEvent.click(screen.getByText('No'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onCancel when backdrop is clicked', async () => {
    const onCancel = vi.fn()
    const { container } = render(
      <ConfirmDialog
        title="Test"
        message="Backdrop?"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    )
    // Backdrop is the first child div's first child (absolute inset-0)
    const backdrop = container.querySelector('.bg-black\\/50')!
    await userEvent.click(backdrop)
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('uses default button labels when not specified', () => {
    render(
      <ConfirmDialog
        title="Test"
        message="Defaults?"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Confirm')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('uses custom button labels', () => {
    render(
      <ConfirmDialog
        title="Test"
        message="Custom?"
        confirmLabel="Remove"
        cancelLabel="Keep"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Remove')).toBeInTheDocument()
    expect(screen.getByText('Keep')).toBeInTheDocument()
  })
})
