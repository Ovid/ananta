import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import UploadArea from '../UploadArea'

describe('UploadArea', () => {
  let onUpload: ReturnType<typeof vi.fn<(files: File[]) => Promise<void>>>

  beforeEach(() => {
    onUpload = vi.fn<(files: File[]) => Promise<void>>().mockResolvedValue(undefined)
  })

  it('renders upload prompt text', () => {
    render(<UploadArea onUpload={onUpload} activeTopic="Barsoom" />)
    expect(screen.getByText('Drop files here or click to upload')).toBeInTheDocument()
  })

  it('has an accessible upload button role', () => {
    render(<UploadArea onUpload={onUpload} activeTopic="Barsoom" />)
    expect(screen.getByRole('button', { name: 'Upload files' })).toBeInTheDocument()
  })

  it('shows uploading state while upload is in progress', async () => {
    let resolveUpload: () => void
    onUpload.mockReturnValue(new Promise<void>(r => { resolveUpload = r }))

    render(<UploadArea onUpload={onUpload} activeTopic="Barsoom" />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['hello'], 'test.txt', { type: 'text/plain' })

    await userEvent.upload(input, file)

    expect(screen.getByText('Uploading...')).toBeInTheDocument()

    resolveUpload!()
    await waitFor(() => {
      expect(screen.getByText('Drop files here or click to upload')).toBeInTheDocument()
    })
  })

  it('calls onUpload with selected files', async () => {
    render(<UploadArea onUpload={onUpload} activeTopic="Barsoom" />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'doc.pdf', { type: 'application/pdf' })

    await userEvent.upload(input, file)

    expect(onUpload).toHaveBeenCalledWith([expect.objectContaining({ name: 'doc.pdf' })])
  })

  it('restores upload state after failure', async () => {
    // onUpload rejects, but UploadArea uses try/finally (no catch), so the
    // caller (App) is responsible for catching. Simulate that by wrapping.
    const rejectingUpload = vi.fn<(files: File[]) => Promise<void>>().mockImplementation(() =>
      Promise.reject(new Error('network error')).catch(() => { /* caller handles */ }),
    )

    render(<UploadArea onUpload={rejectingUpload} activeTopic="Barsoom" />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'], 'bad.txt', { type: 'text/plain' })

    await userEvent.upload(input, file)

    await waitFor(() => {
      expect(screen.getByText('Drop files here or click to upload')).toBeInTheDocument()
    })
  })

  it('disables drop zone when activeTopic is null', () => {
    render(<UploadArea onUpload={vi.fn()} activeTopic={null} />)
    const zone = screen.getByRole('button', { name: /upload/i })
    expect(zone).toHaveAttribute('aria-disabled', 'true')
    expect(zone.textContent?.toLowerCase()).toContain('select a topic')
  })

  it('enables drop zone when activeTopic is provided', () => {
    render(<UploadArea onUpload={vi.fn()} activeTopic="Barsoom" />)
    const zone = screen.getByRole('button', { name: /upload/i })
    expect(zone).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('routes directory drops to onFolderUpload', async () => {
    const onFolderUpload = vi.fn(async () => {})
    const onUpload = vi.fn()
    render(<UploadArea onUpload={onUpload} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

    const fakeDirEntry = { isDirectory: true, isFile: false, name: 'papers', fullPath: '/papers' }
    const dataTransfer = {
      files: [],
      items: [{ webkitGetAsEntry: () => fakeDirEntry }],
    } as unknown as DataTransfer

    const zone = screen.getByRole('button', { name: /upload/i })
    fireEvent.drop(zone, { dataTransfer })

    await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
    expect(onUpload).not.toHaveBeenCalled()
  })

  it('routes plain file drops to onUpload', async () => {
    const onFolderUpload = vi.fn(async () => {})
    const onUpload = vi.fn(async () => {})
    render(<UploadArea onUpload={onUpload} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

    const file = new File(['x'], 'a.md')
    const fakeFileEntry = { isFile: true, isDirectory: false, name: 'a.md', fullPath: '/a.md' }
    const dataTransfer = {
      files: [file],
      items: [{ webkitGetAsEntry: () => fakeFileEntry }],
    } as unknown as DataTransfer

    const zone = screen.getByRole('button', { name: /upload/i })
    fireEvent.drop(zone, { dataTransfer })

    await waitFor(() => expect(onUpload).toHaveBeenCalled())
    expect(onFolderUpload).not.toHaveBeenCalled()
  })
})
