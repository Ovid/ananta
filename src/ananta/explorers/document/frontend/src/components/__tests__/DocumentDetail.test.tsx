import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DocumentDetail from '../DocumentDetail'
import type { DocumentInfo } from '../../types'

const mockDoc: DocumentInfo = {
  project_id: 'doc-abc',
  filename: 'research.pdf',
  content_type: 'application/pdf',
  size: 2048,
  upload_date: '2026-03-01T12:00:00Z',
  page_count: 5,
}

describe('DocumentDetail', () => {
  let onClose: ReturnType<typeof vi.fn<() => void>>
  let onDelete: ReturnType<typeof vi.fn<(id: string) => void>>
  let onAddToTopic: ReturnType<typeof vi.fn<(id: string, topic: string) => void>>
  let onRemoveFromTopic: ReturnType<typeof vi.fn<(id: string, topic: string) => void>>

  beforeEach(() => {
    onClose = vi.fn<() => void>()
    onDelete = vi.fn<(id: string) => void>()
    onAddToTopic = vi.fn<(id: string, topic: string) => void>()
    onRemoveFromTopic = vi.fn<(id: string, topic: string) => void>()
  })

  function renderDetail(overrides: Partial<{
    doc: DocumentInfo
    topics: string[]
    docTopics: string[]
  }> = {}) {
    return render(
      <DocumentDetail
        doc={overrides.doc ?? mockDoc}
        topics={overrides.topics ?? ['chess', 'math']}
        docTopics={overrides.docTopics ?? ['chess']}
        onClose={onClose}
        onDelete={onDelete}
        onAddToTopic={onAddToTopic}
        onRemoveFromTopic={onRemoveFromTopic}
      />,
    )
  }

  it('displays document filename as title', () => {
    renderDetail()
    expect(screen.getByText('research.pdf')).toBeInTheDocument()
  })

  it('displays document metadata', () => {
    renderDetail()
    expect(screen.getByText('application/pdf')).toBeInTheDocument()
    expect(screen.getByText('2 KB')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('renders as a modal dialog', () => {
    renderDetail()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('calls onDelete when Delete button is clicked', async () => {
    renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledWith('doc-abc')
  })

  it('calls onClose when close button is clicked', async () => {
    renderDetail()
    await userEvent.click(screen.getByLabelText('Close'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when Escape is pressed', async () => {
    renderDetail()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows topics the doc belongs to with remove buttons', () => {
    renderDetail({ docTopics: ['chess'] })
    expect(screen.getByText('chess')).toBeInTheDocument()
    expect(screen.getByText('In topics:')).toBeInTheDocument()
  })

  it('calls onRemoveFromTopic when topic remove button is clicked', async () => {
    renderDetail({ docTopics: ['chess'] })
    // The x button next to the topic name
    const topicTag = screen.getByText('chess').closest('span')!
    const removeBtn = topicTag.querySelector('button')!
    await userEvent.click(removeBtn)
    expect(onRemoveFromTopic).toHaveBeenCalledWith('doc-abc', 'chess')
  })

  it('shows "Add to topic" buttons for topics doc is not in', () => {
    renderDetail({ topics: ['chess', 'math'], docTopics: ['chess'] })
    expect(screen.getByText('Add to topic:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ math' })).toBeInTheDocument()
  })

  it('calls onAddToTopic when add-to-topic button is clicked', async () => {
    renderDetail({ topics: ['chess', 'math'], docTopics: ['chess'] })
    await userEvent.click(screen.getByRole('button', { name: '+ math' }))
    expect(onAddToTopic).toHaveBeenCalledWith('doc-abc', 'math')
  })

  it('hides page count when null', () => {
    renderDetail({ doc: { ...mockDoc, page_count: null } })
    expect(screen.queryByText('Pages')).not.toBeInTheDocument()
  })

  it('renders download link', () => {
    renderDetail()
    const link = screen.getByText('Download')
    expect(link).toHaveAttribute('href', '/api/documents/doc-abc/download')
    expect(link).toHaveAttribute('download')
  })
})
