import { describe, it, expect, beforeEach, vi } from 'vitest'
import { api } from '../../api/client'

// Tests for ``api.documents.upload`` — the click-pick / shift-select path.
//
// The folder-upload path (uploadFolderInBatches) was hardened against
// FastAPI auto-422 array details, 413 oversize, and TypeError/SyntaxError
// network failures, but the single-file/click-pick path still routed
// through the shared ``request<T>()`` helper which throws
// ``new Error(err.detail)`` — which stringifies an array detail as
// ``[object Object],[object Object]``. Match the folder-upload UX (I4).
describe('api.documents.upload', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [
        { project_id: 'p1', filename: 'a.md', status: 'created' },
      ],
    } as Response))
  })

  it('returns rows on a 2xx response', async () => {
    const f = new File(['x'], 'a.md', { type: 'text/markdown' })
    const rows = await api.documents.upload([f])
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ filename: 'a.md', status: 'created' })
  })

  it('renders FastAPI auto-422 array detail as a friendly message, not [object Object]', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          {
            loc: ['body', 'relative_path'],
            msg: 'relative_path length must match files length',
            type: 'value_error',
          },
        ],
      }),
    } as Response))
    const f = new File(['x'], 'a.md', { type: 'text/markdown' })
    await expect(api.documents.upload([f])).rejects.toSatisfy((err: unknown) => {
      if (!(err instanceof Error)) return false
      // The bug: ``new Error(detailArray)`` stringifies to
      // ``[object Object]`` (or ``[object Object],[object Object]`` for
      // multi-element arrays). The fix must NOT produce that.
      if (err.message.includes('[object Object]')) return false
      // No raw JSON-array text either.
      if (err.message.includes('"loc"')) return false
      if (err.message.includes('"type"')) return false
      return true
    })
  })

  it('maps 413 to a friendly oversize message', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 413,
      json: async () => ({}),
    } as Response))
    const f = new File(['x'], 'a.md', { type: 'text/markdown' })
    await expect(api.documents.upload([f])).rejects.toSatisfy(
      (err: unknown) => err instanceof Error && /too large/i.test(err.message),
    )
  })

  it('uses FastAPI {detail: string} body when present', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'unsupported file type: .exe' }),
    } as Response))
    const f = new File(['x'], 'a.exe', { type: 'application/octet-stream' })
    await expect(api.documents.upload([f])).rejects.toSatisfy(
      (err: unknown) => err instanceof Error && err.message.includes('unsupported file type'),
    )
  })

  it('omits relative_path entirely when no file has a webkitRelativePath', async () => {
    // U1: appending file.webkitRelativePath unconditionally lets undefined
    // (some webviews / non-browser test harnesses) stringify to the literal
    // string "undefined", which then passes backend validation and lands
    // on disk as a real (bogus) relative_path. Skip the field entirely
    // when no file in the batch carries a real path.
    let captured: FormData | undefined
    global.fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      captured = init?.body as FormData
      return {
        ok: true,
        status: 200,
        json: async () => [{ project_id: 'p1', filename: 'a.md', status: 'created' }],
      } as Response
    })
    const f = new File(['x'], 'a.md', { type: 'text/markdown' })
    // file.webkitRelativePath defaults to '' on a constructed File.
    await api.documents.upload([f])
    expect(captured).toBeDefined()
    expect(captured!.getAll('relative_path')).toEqual([])
    // The files are still attached.
    expect(captured!.getAll('files')).toHaveLength(1)
  })

  it('appends one relative_path per file (length-matched, "" for missing) when any file has a path', async () => {
    // When at least one file carries a webkitRelativePath, the backend
    // requires the relative_path array length to match files length.
    // Coalesce missing/undefined to '' so the length match holds without
    // letting "undefined" leak into a persisted record.
    let captured: FormData | undefined
    global.fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      captured = init?.body as FormData
      return {
        ok: true,
        status: 200,
        json: async () => [
          { project_id: 'p1', filename: 'a.md', status: 'created' },
          { project_id: 'p2', filename: 'b.md', status: 'created' },
        ],
      } as Response
    })
    const a = new File(['x'], 'a.md', { type: 'text/markdown' })
    Object.defineProperty(a, 'webkitRelativePath', {
      value: 'pkg-a/a.md',
      configurable: true,
    })
    const b = new File(['y'], 'b.md', { type: 'text/markdown' })
    // b has the default '' webkitRelativePath
    await api.documents.upload([a, b])
    const paths = captured!.getAll('relative_path')
    expect(paths).toHaveLength(2)
    expect(paths[0]).toBe('pkg-a/a.md')
    // Coalesce — must NOT be "undefined" or any non-string sentinel.
    expect(paths[1]).toBe('')
  })

  it('coalesces a literal undefined webkitRelativePath to empty string', async () => {
    // Some webviews / shimmed test environments expose webkitRelativePath
    // as undefined (not the empty string). FormData.append stringifies
    // undefined to the literal "undefined", which previously passed
    // server-side validation as a real relative_path.
    let captured: FormData | undefined
    global.fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      captured = init?.body as FormData
      return {
        ok: true,
        status: 200,
        json: async () => [
          { project_id: 'p1', filename: 'a.md', status: 'created' },
          { project_id: 'p2', filename: 'b.md', status: 'created' },
        ],
      } as Response
    })
    const a = new File(['x'], 'a.md', { type: 'text/markdown' })
    Object.defineProperty(a, 'webkitRelativePath', {
      value: 'pkg-a/a.md',
      configurable: true,
    })
    const b = new File(['y'], 'b.md', { type: 'text/markdown' })
    Object.defineProperty(b, 'webkitRelativePath', {
      value: undefined,
      configurable: true,
    })
    await api.documents.upload([a, b])
    const paths = captured!.getAll('relative_path')
    expect(paths[1]).toBe('')
    expect(paths[1]).not.toBe('undefined')
  })
})
