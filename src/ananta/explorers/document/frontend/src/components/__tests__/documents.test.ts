import { describe, it, expect, beforeEach, vi } from 'vitest'
import { uploadFolderInBatches } from '../../api/documents'

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
