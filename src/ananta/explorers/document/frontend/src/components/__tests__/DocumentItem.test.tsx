import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { DocumentItem } from '../DocumentItem'
import type { DocumentInfo } from '../../types'

describe('DocumentItem', () => {
  it('renders relative_path as a subtitle when present', () => {
    const doc: DocumentInfo = {
      project_id: 'p1',
      filename: 'README.md',
      content_type: 'text/markdown',
      size: 100,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
      relative_path: 'docs/api/README.md',
      upload_session_id: null,
    }
    render(<DocumentItem doc={doc} />)
    expect(screen.getByText('docs/api/README.md')).toBeInTheDocument()
  })

  it('does not render a path subtitle when relative_path is null', () => {
    const doc: DocumentInfo = {
      project_id: 'p1',
      filename: 'README.md',
      content_type: 'text/markdown',
      size: 100,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
      relative_path: null,
      upload_session_id: null,
    }
    const { container } = render(<DocumentItem doc={doc} />)
    expect(container.querySelector('[data-testid="relative-path"]')).toBeNull()
  })
})
