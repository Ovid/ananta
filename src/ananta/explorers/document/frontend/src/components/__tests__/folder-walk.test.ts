import { describe, it, expect } from 'vitest'
import {
  filterFiles,
  SUPPORTED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
  walkEntries,
  type WalkedFile,
} from '../../lib/folder-walk'

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

type FakeEntry =
  | { isFile: true; isDirectory: false; name: string; fullPath: string; file: (cb: (f: File) => void) => void }
  | { isFile: false; isDirectory: true; name: string; fullPath: string; createReader: () => { readEntries: (cb: (e: FakeEntry[]) => void) => void } }

function makeFile(name: string, fullPath: string, content = ''): FakeEntry {
  return {
    isFile: true,
    isDirectory: false,
    name,
    fullPath,
    file: (cb) => cb(new File([content], name)),
  }
}
function makeDir(name: string, fullPath: string, children: FakeEntry[]): FakeEntry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    fullPath,
    createReader: () => {
      let returned = false
      return {
        readEntries: (cb) => {
          cb(returned ? [] : children)
          returned = true
        },
      }
    },
  }
}

describe('walkEntries', () => {
  it('walks a flat directory and produces relative paths', async () => {
    const root = makeDir('papers', '/papers', [
      makeFile('a.md', '/papers/a.md'),
      makeFile('b.pdf', '/papers/b.pdf'),
    ])
    const result: WalkedFile[] = await walkEntries([root as any], 'papers')
    expect(result.map(r => r.relativePath).sort()).toEqual(['a.md', 'b.pdf'])
  })

  it('walks nested directories and produces relative paths', async () => {
    const root = makeDir('papers', '/papers', [
      makeFile('top.md', '/papers/top.md'),
      makeDir('sub', '/papers/sub', [
        makeFile('x.md', '/papers/sub/x.md'),
      ]),
    ])
    const result = await walkEntries([root as any], 'papers')
    expect(result.map(r => r.relativePath).sort()).toEqual(['sub/x.md', 'top.md'])
  })
})
