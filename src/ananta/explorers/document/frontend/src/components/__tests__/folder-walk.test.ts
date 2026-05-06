import { describe, it, expect } from 'vitest'
import { filterFiles, SUPPORTED_EXTENSIONS, MAX_UPLOAD_BYTES } from '../../lib/folder-walk'

describe('filterFiles', () => {
  it('accepts files with supported extensions under the size limit', () => {
    const files = [
      new File([''], 'a.md'),
      new File([''], 'b.pdf'),
      new File([''], 'd.txt'),
    ]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name).sort()).toEqual(['a.md', 'b.pdf', 'd.txt'])
    expect(skipped).toEqual([])
  })

  it('skips files outside the allowlist with reason "unsupported extension"', () => {
    const files = [
      new File([''], 'a.md'),
      new File([''], 'c.png'),
    ]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name)).toEqual(['a.md'])
    expect(skipped).toEqual([
      { file: expect.objectContaining({ name: 'c.png' }), reason: 'unsupported extension' },
    ])
  })

  it('skips oversized files with reason "file exceeds 50 MB limit"', () => {
    const big = new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], 'big.pdf')
    const files = [new File([''], 'small.pdf'), big]
    const { accepted, skipped } = filterFiles(files)
    expect(accepted.map(f => f.name)).toEqual(['small.pdf'])
    expect(skipped).toEqual([
      { file: expect.objectContaining({ name: 'big.pdf' }), reason: 'file exceeds 50 MB limit' },
    ])
  })

  it('SUPPORTED_EXTENSIONS mirrors the backend allowlist', () => {
    expect(SUPPORTED_EXTENSIONS).toContain('.pdf')
    expect(SUPPORTED_EXTENSIONS).toContain('.md')
    expect(SUPPORTED_EXTENSIONS).toContain('.docx')
    expect(SUPPORTED_EXTENSIONS).not.toContain('.png')
  })
})
