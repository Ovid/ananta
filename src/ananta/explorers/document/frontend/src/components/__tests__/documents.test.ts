import { describe, it, expect, beforeEach, vi } from 'vitest'
import { uploadFolderInBatches, BatchUploadError } from '../../api/documents'

describe('uploadFolderInBatches', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [
        { project_id: 'p1', filename: 'a.md', status: 'created' },
      ],
    } as Response))
  })

  it('sends each batch sequentially and aggregates responses', async () => {
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    const result = await uploadFolderInBatches(batches, 'Barsoom', 'session-uuid', () => {})
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((global.fetch as any).mock.calls.length).toBe(2)
    expect(result.length).toBe(2)
  })

  it('halts after current batch when cancel signal fires', async () => {
    const ctrl = new AbortController()
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
      [{ file: new File(['z'], 'c.md'), relativePath: 'c.md' }],
    ]
    const promise = uploadFolderInBatches(batches, 'Barsoom', 'sid', () => {}, ctrl.signal)
    queueMicrotask(() => ctrl.abort())
    await promise
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((global.fetch as any).mock.calls.length).toBeLessThan(3)
  })

  it('throws BatchUploadError carrying earlier batches\' rows when a later batch fails', async () => {
    // Reproduces C2: the previous code threw a plain Error on a non-OK
    // response, losing all rows accumulated from earlier successful batches.
    // The hook then surfaced "0 ingested" even though batches 1..K-1 were
    // durably committed server-side. Fix: throw BatchUploadError carrying
    // the partial rows so the hook can merge them into the summary.
    let call = 0
    global.fetch = vi.fn(async () => {
      call += 1
      if (call === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { project_id: 'p1', filename: 'a.md', status: 'created' },
          ],
        } as Response
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response
    })
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    await expect(
      uploadFolderInBatches(batches, 'T', 'sid', () => {}),
    ).rejects.toSatisfy((err: unknown) => {
      if (!(err instanceof BatchUploadError)) return false
      if (err.partial.length !== 1) return false
      return err.partial[0].filename === 'a.md' && err.partial[0].status === 'created'
    })
  })

  it('throws BatchUploadError on a fetch rejection, carrying earlier rows (I2)', async () => {
    // The C2 fix only handled the !res.ok branch. A network drop, DNS
    // failure, or mid-body abort makes fetch() reject with a plain
    // TypeError, which previously bubbled past the hook's
    // `instanceof BatchUploadError` guard and stranded the rows from any
    // batches that had already committed server-side. This test pins the
    // contract: every error path through the function must surface as a
    // BatchUploadError carrying `partial`.
    let call = 0
    global.fetch = vi.fn(async () => {
      call += 1
      if (call === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { project_id: 'p1', filename: 'a.md', status: 'created' },
          ],
        } as Response
      }
      throw new TypeError('Failed to fetch')
    })
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    await expect(
      uploadFolderInBatches(batches, 'T', 'sid', () => {}),
    ).rejects.toSatisfy((err: unknown) => {
      if (!(err instanceof BatchUploadError)) return false
      if (err.partial.length !== 1) return false
      return err.partial[0].filename === 'a.md' && err.partial[0].status === 'created'
    })
  })

  it('throws BatchUploadError on a malformed res.json(), carrying earlier rows (I2)', async () => {
    // res.json() throwing (e.g., body already consumed, malformed JSON
    // from a misbehaving proxy) is the same bug class as a fetch rejection
    // — it must surface as BatchUploadError so partial rows survive.
    let call = 0
    global.fetch = vi.fn(async () => {
      call += 1
      if (call === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { project_id: 'p1', filename: 'a.md', status: 'created' },
          ],
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected end of JSON input')
        },
      } as Response
    })
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    await expect(
      uploadFolderInBatches(batches, 'T', 'sid', () => {}),
    ).rejects.toSatisfy((err: unknown) => err instanceof BatchUploadError && err.partial.length === 1)
  })

  it('maps 413 to a friendly error message (I9)', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 413,
      json: async () => ({}),
    } as Response))
    const batches = [[{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]]
    await expect(uploadFolderInBatches(batches, 'T', 'sid', () => {})).rejects.toSatisfy(
      (err: unknown) => err instanceof BatchUploadError && err.message.includes('files too large'),
    )
  })

  it('uses FastAPI {detail} body when present (I9)', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'relative_path length must match files length' }),
    } as Response))
    const batches = [[{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]]
    await expect(uploadFolderInBatches(batches, 'T', 'sid', () => {})).rejects.toSatisfy(
      (err: unknown) =>
        err instanceof BatchUploadError &&
        err.message.includes('relative_path length must match files length'),
    )
  })

  it('reports progress to the callback', async () => {
    const onProgress = vi.fn()
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    await uploadFolderInBatches(batches, 'Barsoom', 'sid', onProgress)
    expect(onProgress).toHaveBeenCalledWith(1, 2, 1, 2)
    expect(onProgress).toHaveBeenCalledWith(2, 2, 2, 2)
  })
})
