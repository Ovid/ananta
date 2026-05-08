import { describe, it, expect } from 'vitest'
import {
  filterFiles,
  SUPPORTED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
  MAX_FOLDER_FILES,
  walkEntries,
  partitionIntoBatches,
  TARGET_BATCH_BYTES,
  type WalkedFile,
} from '../../lib/folder-walk'

describe('filterFiles', () => {
  const wf = (name: string, content: string | Uint8Array = '', relativePath?: string): WalkedFile => ({
    file: new File([content], name),
    relativePath: relativePath ?? name,
  })

  it('accepts files with supported extensions under the size limit', () => {
    const walked = [wf('a.md'), wf('b.pdf'), wf('d.txt')]
    const { accepted, skipped } = filterFiles(walked)
    expect(accepted.map(w => w.file.name).sort()).toEqual(['a.md', 'b.pdf', 'd.txt'])
    expect(skipped).toEqual([])
  })

  it('skips files outside the allowlist with reason "unsupported extension"', () => {
    const walked = [wf('a.md'), wf('c.png', '', 'sub/c.png')]
    const { accepted, skipped } = filterFiles(walked)
    expect(accepted.map(w => w.file.name)).toEqual(['a.md'])
    expect(skipped).toEqual([
      {
        file: expect.objectContaining({ name: 'c.png' }),
        relativePath: 'sub/c.png',
        reason: 'unsupported extension',
      },
    ])
  })

  it('skips oversized files with reason "file exceeds 50 MB limit"', () => {
    const walked = [
      wf('small.pdf'),
      wf('big.pdf', new Uint8Array(MAX_UPLOAD_BYTES + 1), 'docs/big.pdf'),
    ]
    const { accepted, skipped } = filterFiles(walked)
    expect(accepted.map(w => w.file.name)).toEqual(['small.pdf'])
    expect(skipped).toEqual([
      {
        file: expect.objectContaining({ name: 'big.pdf' }),
        relativePath: 'docs/big.pdf',
        reason: 'file exceeds 50 MB limit',
      },
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

describe('walkEntries with cap', () => {
  it('throws when the file count exceeds MAX_FOLDER_FILES', async () => {
    const children = Array.from({ length: MAX_FOLDER_FILES + 100 }, (_, i) =>
      makeFile(`f${i}.md`, `/big/f${i}.md`)
    )
    const root = makeDir('big', '/big', children)
    await expect(walkEntries([root as any], 'big'))
      .rejects.toThrow(/folder.*limit/i)
  })

  it('accepts exactly MAX_FOLDER_FILES files (off-by-one regression S1)', async () => {
    const children = Array.from({ length: MAX_FOLDER_FILES }, (_, i) =>
      makeFile(`f${i}.md`, `/big/f${i}.md`)
    )
    const root = makeDir('big', '/big', children)
    const result = await walkEntries([root as any], 'big')
    expect(result.length).toBe(MAX_FOLDER_FILES)
  })

  it('does not throw when the cap is exceeded only by unsupported files (Inline 5)', async () => {
    // Dropping a folder with many unsupported files (e.g., a git checkout
    // full of .png/.svg assets) but only a few supported source files must
    // not trip the cap. The previous implementation counted raw files and
    // would reject the whole folder.
    const accepted = Array.from({ length: 10 }, (_, i) =>
      makeFile(`src${i}.md`, `/repo/src${i}.md`)
    )
    const unsupported = Array.from({ length: MAX_FOLDER_FILES + 200 }, (_, i) =>
      makeFile(`asset${i}.png`, `/repo/asset${i}.png`)
    )
    const root = makeDir('repo', '/repo', [...accepted, ...unsupported])
    const result = await walkEntries([root as any], 'repo')
    // walkEntries returns every walked file; the hook re-runs filterFiles
    // to categorise them. The point is that the cap did not throw.
    expect(result.length).toBe(MAX_FOLDER_FILES + 210)
  })

  it('throws on the (MAX_FOLDER_FILES + 1)th accepted file (Inline 5)', async () => {
    // Boundary check: 501 accepted files must exceed the cap. The previous
    // ">"-comparison would push this through up to 502 before throwing.
    const children = Array.from({ length: MAX_FOLDER_FILES + 1 }, (_, i) =>
      makeFile(`f${i}.md`, `/big/f${i}.md`)
    )
    const root = makeDir('big', '/big', children)
    await expect(walkEntries([root as any], 'big'))
      .rejects.toThrow(/folder.*limit/i)
  })
})

describe('walkEntries multi-folder drop (I4)', () => {
  // Reproduces I4: when multiple top-level directories are dropped, the
  // previous implementation stripped only the first folder's prefix from
  // every file's relativePath. Files from secondary folders retained
  // their root in the persisted path.
  it('strips each top-level folder\'s own prefix', async () => {
    const folderA = makeDir('folderA', '/folderA', [
      makeFile('a.md', '/folderA/a.md'),
    ])
    const folderB = makeDir('folderB', '/folderB', [
      makeFile('b.md', '/folderB/b.md'),
    ])
    // rootName is kept as the first folder for backward compat (the modal
    // labels the upload after the first dropped folder); the stripping
    // logic must derive the per-entry root internally.
    const result = await walkEntries([folderA as any, folderB as any], 'folderA')
    const paths = result.map(r => r.relativePath).sort()
    // Without the fix, b.md ends up as 'folderB/b.md' because folderB's
    // prefix is never stripped.
    expect(paths).toEqual(['a.md', 'b.md'])
  })
})

describe('walkEntries error resilience (I8)', () => {
  // Reproduces I8: a single getFile failure (permission, OS quirk, race
  // with file deletion) previously rejected the entire walk. The user
  // saw a single "skipped" row with no per-file detail and lost
  // visibility into which files were readable. Wrap each entry visit so
  // a failure on one file doesn't abandon the rest.
  it('continues walking when a single file getFile rejects', async () => {
    const goodA = makeFile('a.md', '/repo/a.md')
    const broken: FakeEntry = {
      isFile: true,
      isDirectory: false,
      name: 'broken.md',
      fullPath: '/repo/broken.md',
      file: (_cb, errCb?: (err: Error) => void) => {
        if (errCb) errCb(new Error('permission denied'))
      },
    } as FakeEntry
    const goodB = makeFile('b.md', '/repo/b.md')
    const root = makeDir('repo', '/repo', [goodA, broken, goodB])
    const result = await walkEntries([root as any], 'repo')
    // The two readable files survive; the broken one is dropped silently
    // (the hook's preflight categorises filtering, but we expect at minimum
    // not to throw).
    const names = result.map(r => r.relativePath).sort()
    expect(names).toContain('a.md')
    expect(names).toContain('b.md')
  })
})

describe('partitionIntoBatches', () => {
  it('groups files under the target byte size', () => {
    const files = [
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'a.pdf'), relativePath: 'a.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'b.pdf'), relativePath: 'b.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'c.pdf'), relativePath: 'c.pdf' },
    ]
    const batches = partitionIntoBatches(files, TARGET_BATCH_BYTES)
    expect(batches.length).toBe(2)
    expect(batches[0].length).toBe(2)
    expect(batches[1].length).toBe(1)
  })

  it('places a single file in its own batch when adding the next would exceed target', () => {
    const files = [
      { file: new File([new Uint8Array(40 * 1024 * 1024)], 'big.pdf'), relativePath: 'big.pdf' },
      { file: new File([new Uint8Array(20 * 1024 * 1024)], 'small.pdf'), relativePath: 'small.pdf' },
    ]
    const batches = partitionIntoBatches(files, 50 * 1024 * 1024)
    expect(batches.length).toBe(2)
  })

  it('returns an empty array for empty input', () => {
    expect(partitionIntoBatches([], TARGET_BATCH_BYTES)).toEqual([])
  })
})
