import { describe, it, expect } from 'vitest'
import { docToDocumentItem } from '../DocumentItem'
import type { DocumentInfo } from '../../types'

describe('docToDocumentItem', () => {
  it('threads relative_path into the subtitle field for visible rendering', () => {
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
    const item = docToDocumentItem(doc)
    expect(item.subtitle).toBe('docs/api/README.md')
  })

  it('omits subtitle when relative_path is null', () => {
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
    const item = docToDocumentItem(doc)
    expect(item.subtitle).toBeUndefined()
  })

  it('omits subtitle when relative_path equals filename (root-level folder upload)', () => {
    const doc: DocumentInfo = {
      project_id: 'p1',
      filename: 'README.md',
      content_type: 'text/markdown',
      size: 100,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
      relative_path: 'README.md',
      upload_session_id: null,
    }
    const item = docToDocumentItem(doc)
    expect(item.subtitle).toBeUndefined()
  })

  it('omits subtitle when relative_path is missing', () => {
    const doc: DocumentInfo = {
      project_id: 'p1',
      filename: 'README.md',
      content_type: 'text/markdown',
      size: 100,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
    }
    const item = docToDocumentItem(doc)
    expect(item.subtitle).toBeUndefined()
  })

  it('still sets sublabel (size+icon) for tooltip', () => {
    const doc: DocumentInfo = {
      project_id: 'p1',
      filename: 'README.md',
      content_type: 'text/plain',
      size: 100,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
      relative_path: 'a/b/README.md',
    }
    const item = docToDocumentItem(doc)
    expect(item.sublabel).toMatch(/100 B/)
  })

  it('matches FILE_ICONS by base type even when content_type carries a charset suffix (S37)', () => {
    // Browsers may send "text/plain; charset=utf-8" and the backend stores
    // ``UploadFile.content_type`` verbatim. The previous exact-match
    // lookup missed this and fell through to the default folder icon.
    const plain: DocumentInfo = {
      project_id: 'p1',
      filename: 'a.txt',
      content_type: 'text/plain',
      size: 10,
      upload_date: '2026-05-05T00:00:00Z',
      page_count: null,
    }
    const plainWithCharset: DocumentInfo = {
      ...plain,
      project_id: 'p2',
      content_type: 'text/plain; charset=utf-8',
    }
    const a = docToDocumentItem(plain)
    const b = docToDocumentItem(plainWithCharset)
    // Both should produce the same icon prefix (the size suffix differs
    // only when sizes differ — they are equal here).
    expect(b.sublabel).toBe(a.sublabel)
  })
})
