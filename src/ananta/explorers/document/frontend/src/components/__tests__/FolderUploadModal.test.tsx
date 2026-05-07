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
})
