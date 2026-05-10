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

  it("renders FastAPI auto-422 array detail as a friendly message, not a JSON blob (S2)", async () => {
    // FastAPI's automatic Pydantic-validation 422 carries an array of
    // {loc, msg, type} objects, not a string. JSON-stringifying the array
    // produces a useless toast like
    //   upload failed: [{"loc":["body","new_name"],"msg":"...","type":"..."}]
    // Practically rare on this route (most 422s are manual HTTPException
    // with string detail), but worth fixing — the array-detail branch
    // should fall back to the friendly status-code phrase rather than
    // dumping JSON at the user.
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          {
            loc: ['body', 'new_name'],
            msg: 'ensure this value has at most 512 characters',
            type: 'value_error.any_str.max_length',
          },
        ],
      }),
    } as Response))
    const batches = [[{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]]
    await expect(uploadFolderInBatches(batches, 'T', 'sid', () => {})).rejects.toSatisfy(
      (err: unknown) => {
        if (!(err instanceof BatchUploadError)) return false
        // No raw JSON-array text in the message (no "[" or "loc" or
        // "type":).
        if (err.message.includes('"loc"')) return false
        if (err.message.includes('"type"')) return false
        if (/^upload failed: \[/.test(err.message)) return false
        return true
      },
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

  it('currentBatch label advances BEFORE batch K\'s fetch resolves (I5)', async () => {
    // Bug: onProgress was only fired AFTER each batch completed, with the
    // batch index that had just finished. The hook initialised currentBatch=1
    // for batch 1 (so batch 1 displays correctly), but for batches 2+ the
    // label only ticked AFTER they finished — so during batch K (K>=2) the
    // modal still showed "batch K-1 of N". Fix: also emit a "batch starting"
    // callback at the top of each iteration BEFORE awaiting fetch, so the
    // label advances to K before batch K's network round-trip.
    const fetchCalls: number[] = []
    const progressCalls: { completed: number; currentBatch: number }[] = []
    let resolveFetch: (() => void) | null = null
    global.fetch = vi.fn(async () => {
      // Block on a manually-resolved promise so the test can observe what
      // onProgress has been called with BEFORE fetch resolves.
      fetchCalls.push(fetchCalls.length + 1)
      await new Promise<void>(resolve => {
        resolveFetch = resolve
      })
      return {
        ok: true,
        status: 200,
        json: async () => [
          { project_id: 'p', filename: 'x.md', status: 'created' },
        ],
      } as Response
    })
    const onProgress = (
      completed: number,
      _total: number,
      currentBatch: number,
      _totalBatches: number,
    ): void => {
      progressCalls.push({ completed, currentBatch })
    }
    const batches = [
      [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }],
      [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }],
    ]
    const promise = uploadFolderInBatches(batches, 'Barsoom', 'sid', onProgress)

    // Drain microtasks until fetch is in-flight for batch 1.
    await Promise.resolve()
    await Promise.resolve()
    // Batch 1 is in flight. There must already be a progress emission for
    // currentBatch=1 (this is the starting event; without it the modal
    // would briefly read "batch 0 of N").
    expect(progressCalls.some(c => c.currentBatch === 1)).toBe(true)
    // No progress emission for batch 2 yet — we haven't gotten there.
    expect(progressCalls.some(c => c.currentBatch === 2)).toBe(false)

    // Resolve batch 1's fetch and wait for batch 2 to start its fetch.
    resolveFetch!()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    // Batch 2's starting emission must arrive BEFORE its fetch resolves.
    expect(progressCalls.some(c => c.currentBatch === 2)).toBe(true)

    // Resolve batch 2 and let the upload finish.
    resolveFetch!()
    await promise
  })
})
