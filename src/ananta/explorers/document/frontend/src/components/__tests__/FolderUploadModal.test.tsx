import { render, screen, fireEvent } from '@testing-library/react'
import FolderUploadModal from '../FolderUploadModal'
import { SOFT_WARN_FOLDER_FILES } from '../../lib/folder-walk'

describe('FolderUploadModal pre-flight', () => {
  const baseFiles = [
    { file: new File(['x'], 'a.md'), relativePath: 'a.md' },
    { file: new File(['y'], 'b.md'), relativePath: 'sub/b.md' },
  ]

  it('renders target topic, file count, and total bytes', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/Barsoom/)).toBeInTheDocument()
    expect(screen.getByText(/2 files/i)).toBeInTheDocument()
  })

  it('shows soft warning above SOFT_WARN_FOLDER_FILES', () => {
    const many = Array.from({ length: SOFT_WARN_FOLDER_FILES + 50 }, (_, i) => ({
      file: new File(['x'], `f${i}.md`),
      relativePath: `f${i}.md`,
    }))
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: many, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('does not show soft warning at or below SOFT_WARN_FOLDER_FILES', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('groups skipped files by reason', () => {
    render(
      <FolderUploadModal
        state={{
          kind: 'preflight',
          accepted: baseFiles,
          skipped: [
            { file: new File([''], 'x.png'), reason: 'unsupported extension' },
            { file: new File([''], 'y.png'), reason: 'unsupported extension' },
            { file: new File([''], 'big.pdf'), reason: 'file exceeds 50 MB limit' },
          ],
          targetTopic: 'Barsoom',
        }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/2.*unsupported extension/i)).toBeInTheDocument()
    expect(screen.getByText(/1.*exceeds 50 MB/i)).toBeInTheDocument()
  })

  it('calls onContinue when Continue clicked', () => {
    const onContinue = vi.fn()
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={onContinue}
        onCancel={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(onContinue).toHaveBeenCalled()
  })

  it('Continue button is disabled when there are no accepted files (I3)', () => {
    // A folder with only unsupported / oversized files reaches preflight
    // with accepted=[]. Pressing Continue from that state used to build zero
    // batches, transition to progress with a nonsensical "batch 1 of 0",
    // bump commitVersion, and fire a needless refetch. Disable Continue at
    // the source so the user can only Cancel.
    const onContinue = vi.fn()
    render(
      <FolderUploadModal
        state={{
          kind: 'preflight',
          accepted: [],
          skipped: [{ file: new File([''], 'logo.png'), reason: 'unsupported extension' }],
          targetTopic: 'Barsoom',
        }}
        onContinue={onContinue}
        onCancel={() => {}}
      />
    )
    const button = screen.getByRole('button', { name: /continue/i })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(onContinue).not.toHaveBeenCalled()
  })

  it('Continue button disables on click and ignores rapid second clicks (I7)', () => {
    const onContinue = vi.fn()
    render(
      <FolderUploadModal
        state={{ kind: 'preflight', accepted: baseFiles, skipped: [], targetTopic: 'Barsoom' }}
        onContinue={onContinue}
        onCancel={() => {}}
      />
    )
    const button = screen.getByRole('button', { name: /continue/i })
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)
    expect(onContinue).toHaveBeenCalledTimes(1)
    expect(button).toBeDisabled()
  })
})

describe('FolderUploadModal progress', () => {
  it('renders a progress indicator', () => {
    render(
      <FolderUploadModal
        state={{ kind: 'progress', total: 100, completed: 30, currentBatch: 2, totalBatches: 5 }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/30 of 100/)).toBeInTheDocument()
    expect(screen.getByText(/batch 2 of 5/i)).toBeInTheDocument()
  })

  it('cancel button is enabled', () => {
    const onCancel = vi.fn()
    render(
      <FolderUploadModal
        state={{ kind: 'progress', total: 100, completed: 30, currentBatch: 2, totalBatches: 5 }}
        onContinue={() => {}}
        onCancel={onCancel}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})

describe('FolderUploadModal summary', () => {
  it('renders ingested / failed / skipped rows', () => {
    render(
      <FolderUploadModal
        state={{
          kind: 'summary',
          ingested: 47,
          failed: [{ name: 'bad.pdf', reason: 'text extraction failed' }],
          skipped: [{ name: 'logo.png', reason: 'unsupported extension' }],
        }}
        onContinue={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText(/47/)).toBeInTheDocument()
    expect(screen.getByText('bad.pdf')).toBeInTheDocument()
    expect(screen.getByText('logo.png')).toBeInTheDocument()
  })
})
