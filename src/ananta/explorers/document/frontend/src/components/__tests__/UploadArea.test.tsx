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
    const zone = screen.getByRole('button', { name: 'Upload files' })
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

    const zone = screen.getByRole('button', { name: 'Upload files' })
    fireEvent.drop(zone, { dataTransfer })

    await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
    expect(onUpload).not.toHaveBeenCalled()
  })

  it('falls back to onUpload when webkitGetAsEntry is not available on items', async () => {
    // Defensive: webkitGetAsEntry is non-standard. Some webviews / older
    // browsers / test harnesses can deliver DataTransferItems without it.
    // The previous unconditional type-cast threw, taking down ALL drag-drop
    // (even plain file drops). Verify a safe fallback to handleFiles.
    const onFolderUpload = vi.fn(async () => {})
    const onUpload = vi.fn(async () => {})
    render(<UploadArea onUpload={onUpload} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

    const file = new File(['x'], 'a.md')
    // items[0] has NO webkitGetAsEntry property — simulates the unsupported
    // browser. files[] is the plain file list.
    const dataTransfer = {
      files: [file],
      items: [{ kind: 'file', type: 'text/markdown' }],
    } as unknown as DataTransfer

    const zone = screen.getByRole('button', { name: 'Upload files' })
    fireEvent.drop(zone, { dataTransfer })

    await waitFor(() => expect(onUpload).toHaveBeenCalled())
    expect(onFolderUpload).not.toHaveBeenCalled()
    expect(onUpload).toHaveBeenCalledWith([expect.objectContaining({ name: 'a.md' })])
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

    const zone = screen.getByRole('button', { name: 'Upload files' })
    fireEvent.drop(zone, { dataTransfer })

    await waitFor(() => expect(onUpload).toHaveBeenCalled())
    expect(onFolderUpload).not.toHaveBeenCalled()
  })

  it('renders an "Upload folder" button when enabled', () => {
    render(<UploadArea onUpload={vi.fn()} onFolderUpload={vi.fn()} activeTopic="Barsoom" />)
    expect(screen.getByRole('button', { name: /upload folder/i })).toBeInTheDocument()
  })

  it('does not render "Upload folder" when no topic selected', () => {
    render(<UploadArea onUpload={vi.fn()} onFolderUpload={vi.fn()} activeTopic={null} />)
    expect(screen.queryByRole('button', { name: /upload folder/i })).toBeNull()
  })

  it('resets the folder input value after a selection so re-picking the same folder fires change (Inline 6)', async () => {
    const onFolderUpload = vi.fn(async () => {})
    render(<UploadArea onUpload={vi.fn()} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

    const file = new File(['x'], 'a.md')
    Object.defineProperty(file, 'webkitRelativePath', { value: 'papers/a.md' })

    const folderInput = screen.getByLabelText(/folder picker/i) as HTMLInputElement
    // Spy on the value-setter so we can detect the post-change reset. Browsers
    // forbid setting non-empty strings on input[type=file] from JS, so the
    // only assignment we expect is `''`.
    const valueAssignments: string[] = []
    const proto = Object.getPrototypeOf(folderInput)
    const originalDescriptor = Object.getOwnPropertyDescriptor(proto, 'value')!
    Object.defineProperty(folderInput, 'value', {
      configurable: true,
      get: () => originalDescriptor.get!.call(folderInput),
      set: (v: string) => {
        valueAssignments.push(v)
        originalDescriptor.set!.call(folderInput, v)
      },
    })

    Object.defineProperty(folderInput, 'files', { value: [file], writable: true })
    fireEvent.change(folderInput)

    await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
    // The handler must clear .value so re-picking the same folder fires
    // change again — browsers won't fire change for the same value twice.
    expect(valueAssignments).toContain('')
  })

  it('routes click-selected folder files to onFolderUpload as WalkedFile[]', async () => {
    const onFolderUpload = vi.fn(async () => {})
    render(<UploadArea onUpload={vi.fn()} onFolderUpload={onFolderUpload} activeTopic="Barsoom" />)

    const file1 = new File(['x'], 'a.md')
    Object.defineProperty(file1, 'webkitRelativePath', { value: 'papers/a.md' })
    const file2 = new File(['y'], 'b.md')
    Object.defineProperty(file2, 'webkitRelativePath', { value: 'papers/sub/b.md' })

    const folderInput = screen.getByLabelText(/folder picker/i) as HTMLInputElement
    Object.defineProperty(folderInput, 'files', { value: [file1, file2], writable: false })
    fireEvent.change(folderInput)

    await waitFor(() => expect(onFolderUpload).toHaveBeenCalled())
    const [arg] = onFolderUpload.mock.calls[0]
    expect(arg.kind).toBe('walked')
    expect(arg.rootName).toBe('papers')
    expect(arg.files.map((w: { relativePath: string }) => w.relativePath).sort()).toEqual(['a.md', 'sub/b.md'])
  })
})
