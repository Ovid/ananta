import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useFolderUpload } from '../../lib/use-folder-upload'
import * as documentsApi from '../../api/documents'
import type { UploadRow } from '../../api/documents'

describe('useFolderUpload', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('starts with no state', () => {
    const { result } = renderHook(() => useFolderUpload())
    expect(result.current.state).toBeNull()
  })

  it('walking entries transitions to preflight', async () => {
    const fakeFile = {
      isFile: true,
      isDirectory: false,
      name: 'a.md',
      fullPath: '/x/a.md',
      file: (cb: (f: File) => void) => cb(new File(['x'], 'a.md')),
    }
    const fakeRoot = {
      isFile: false,
      isDirectory: true,
      name: 'x',
      fullPath: '/x',
      createReader: () => {
        let r = false
        return {
          readEntries: (cb: (entries: unknown[]) => void) => {
            cb(r ? [] : [fakeFile])
            r = true
          },
        }
      },
    }
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { kind: 'entries', entries: [fakeRoot as any], rootName: 'x' },
        'Barsoom',
      )
    })
    expect(result.current.state?.kind).toBe('preflight')
  })

  it('walked-file path transitions to preflight without re-walking', async () => {
    const files = [
      { file: new File(['x'], 'a.md'), relativePath: 'a.md' },
      { file: new File(['y'], 'b.md'), relativePath: 'sub/b.md' },
    ]
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    expect(result.current.state?.kind).toBe('preflight')
  })

  it('confirm carries pre-flight skipped rows through to summary', async () => {
    // Mix of accepted (.md) and skipped (.png — unsupported extension).
    const files = [
      { file: new File(['x'], 'a.md'), relativePath: 'a.md' },
      { file: new File(['y'], 'oops.png'), relativePath: 'oops.png' },
    ]
    const uploadSpy = vi
      .spyOn(documentsApi, 'uploadFolderInBatches')
      .mockResolvedValue([
        { project_id: 'p1', filename: 'a.md', status: 'created' },
      ])

    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    expect(result.current.state?.kind).toBe('preflight')

    await act(async () => {
      await result.current.confirm()
    })

    expect(uploadSpy).toHaveBeenCalled()
    expect(result.current.state?.kind).toBe('summary')
    if (result.current.state?.kind === 'summary') {
      expect(result.current.state.ingested).toBe(1)
      expect(result.current.state.skipped).toEqual([
        { name: 'oops.png', reason: 'unsupported extension' },
      ])
    }
  })

  it('walked path enforces MAX_FOLDER_FILES cap', async () => {
    // The click-folder picker hands the hook a pre-walked file list, skipping
    // the entries->walk path. Without this guard, drag-drop enforces the cap
    // but click-folder does not (I3).
    const files = Array.from({ length: 501 }, (_, i) => ({
      file: new File(['x'], `f${i}.md`),
      relativePath: `f${i}.md`,
    }))
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'big' }, 'Barsoom')
    })
    expect(result.current.state?.kind).toBe('summary')
    if (result.current.state?.kind === 'summary') {
      expect(result.current.state.ingested).toBe(0)
      expect(result.current.state.skipped).toEqual([
        { name: 'big', reason: expect.stringMatching(/folder.*limit/i) },
      ])
    }
  })

  it('summary includes earlier batches\' rows when later batch fails (C2)', async () => {
    // Reproduces C2: when batch K fails, batches 1..K-1 are durably committed
    // server-side. The hook must merge those rows into the summary, not
    // present "0 ingested" alongside the failure.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    const partial = [
      { project_id: 'p1', filename: 'first.md', status: 'created' as const },
      { project_id: 'p2', filename: 'second.md', status: 'created' as const },
    ]
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockImplementation(async () => {
      throw new documentsApi.BatchUploadError('upload failed: 500', partial)
    })
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'T')
    })
    await act(async () => {
      await result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('summary')
    if (result.current.state?.kind === 'summary') {
      // The two earlier-batch successes must be reflected as "ingested".
      expect(result.current.state.ingested).toBe(2)
      // The error reason must still appear in failed rows.
      expect(result.current.state.failed.some(f => /upload failed/.test(f.reason))).toBe(true)
    }
  })

  it('upload error transitions to summary with the error reason', async () => {
    // confirm() previously had no catch around uploadFolderInBatches: a
    // non-OK response (e.g., 413) or fetch failure left the modal stuck on
    // 'progress' with no error info, no failed-row reporting, and only a
    // Cancel button (I4).
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockRejectedValue(
      new Error('upload failed: 500'),
    )
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    await act(async () => {
      await result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('summary')
    if (result.current.state?.kind === 'summary') {
      // The error must appear somewhere in the summary so the user sees what
      // went wrong instead of being stranded on progress.
      const allReasons = [
        ...result.current.state.failed.map(f => f.reason),
        ...result.current.state.skipped.map(s => s.reason),
      ]
      expect(allReasons.some(r => r.includes('upload failed'))).toBe(true)
    }
  })

  it('commitVersion bumps after summary so App can refresh docs', async () => {
    // After a successful upload, commitVersion increments exactly once so a
    // useEffect can observe it and refresh the document list (I5 motivates
    // exposing this signal so the cancel-mid-flight path can also bump it).
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockResolvedValue([
      { project_id: 'p1', filename: 'a.md', status: 'created' },
    ])
    const { result } = renderHook(() => useFolderUpload())
    expect(result.current.commitVersion).toBe(0)

    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    expect(result.current.commitVersion).toBe(0)

    await act(async () => {
      await result.current.confirm()
    })
    expect(result.current.commitVersion).toBe(1)
  })

  it('commitVersion bumps when cancel fires after a batch completes', async () => {
    // The in-flight batch always commits server-side before cancel is honoured
    // (documented in api/documents.ts). The user-visible bug (I5): the doc
    // list stayed stale after such a cancel. commitVersion now bumps on
    // cancel-from-progress so the sidebar can refresh.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    let resolveUpload: (rows: UploadRow[]) => void = () => {}
    const uploadPromise = new Promise<UploadRow[]>((resolve) => {
      resolveUpload = resolve
    })
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockImplementation(
      async () => uploadPromise,
    )
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })

    let confirmPromise: Promise<void> = Promise.resolve()
    act(() => {
      confirmPromise = result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('progress')
    expect(result.current.commitVersion).toBe(0)

    act(() => {
      result.current.cancel()
    })
    expect(result.current.commitVersion).toBe(1)

    await act(async () => {
      resolveUpload([{ project_id: 'p1', filename: 'a.md', status: 'created' }])
      await confirmPromise
    })
    // After the in-flight batch resolves, the cancel-already-fired bump
    // should not double-increment.
    expect(result.current.commitVersion).toBe(1)
  })

  it('commitVersion does not bump when cancel fires before any upload', async () => {
    // Cancel from preflight discards no committed batches, so no refresh is
    // needed and commitVersion must stay at 0.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    expect(result.current.state?.kind).toBe('preflight')
    act(() => {
      result.current.cancel()
    })
    expect(result.current.commitVersion).toBe(0)
  })

  it('initial progress state shows batch 1, not batch 0', async () => {
    // The modal renders "(batch X of N)" using state.currentBatch. If the
    // initial progress state is currentBatch=0 the user briefly sees
    // "batch 0 of N" before the first onProgress fires. Initialise to 1 so
    // the user always sees a 1-based batch count.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    let resolveUpload: (rows: UploadRow[]) => void = () => {}
    const uploadPromise = new Promise<UploadRow[]>((resolve) => {
      resolveUpload = resolve
    })
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockImplementation(
      async () => uploadPromise,
    )
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    let confirmPromise: Promise<void> = Promise.resolve()
    act(() => {
      confirmPromise = result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('progress')
    if (result.current.state?.kind === 'progress') {
      expect(result.current.state.currentBatch).toBe(1)
    }
    await act(async () => {
      resolveUpload([{ project_id: 'p1', filename: 'a.md', status: 'created' }])
      await confirmPromise
    })
  })

  it('confirm is a no-op when an upload is already in flight (double-click guard)', async () => {
    // Reproduces I7: a second confirm() call from a double-click (touch screen,
    // accessibility tools, queued events) must not start a second upload.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    let resolveUpload: (rows: UploadRow[]) => void = () => {}
    const uploadPromise = new Promise<UploadRow[]>((resolve) => {
      resolveUpload = resolve
    })
    const uploadSpy = vi
      .spyOn(documentsApi, 'uploadFolderInBatches')
      .mockImplementation(async () => uploadPromise)

    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })

    // First confirm — keep the upload pending.
    let firstConfirm: Promise<void> = Promise.resolve()
    act(() => {
      firstConfirm = result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('progress')
    expect(uploadSpy).toHaveBeenCalledTimes(1)

    // Second confirm — must be a no-op while the first is still in flight.
    await act(async () => {
      await result.current.confirm()
    })
    expect(uploadSpy).toHaveBeenCalledTimes(1)

    // Resolve the first upload so the test cleans up.
    await act(async () => {
      resolveUpload([{ project_id: 'p1', filename: 'a.md', status: 'created' }])
      await firstConfirm
    })
  })

  it('finally clause does not clobber a newer upload\'s abort controller (C3)', async () => {
    // Reproduces C3: upload A's finally{} runs after A is cancelled and B has
    // started. A's finally{} previously did `abortCtlRef.current = null`
    // unconditionally, wiping B's controller. A subsequent cancel() then saw
    // null and could NOT abort B's in-flight signal. Fix: only null if the
    // ref still points at our own controller.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    let resolveA: (rows: UploadRow[]) => void = () => {}
    let resolveB: (rows: UploadRow[]) => void = () => {}
    const promiseA = new Promise<UploadRow[]>((r) => { resolveA = r })
    const promiseB = new Promise<UploadRow[]>((r) => { resolveB = r })
    let signalB: AbortSignal | undefined
    const uploadSpy = vi.spyOn(documentsApi, 'uploadFolderInBatches')
    uploadSpy.mockImplementationOnce(async () => promiseA)
    uploadSpy.mockImplementationOnce(async (_b, _t, _s, _p, signal) => {
      signalB = signal
      return promiseB
    })

    const { result } = renderHook(() => useFolderUpload())

    // Upload A: start, confirm, then cancel.
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'T')
    })
    let confirmA: Promise<void> = Promise.resolve()
    act(() => { confirmA = result.current.confirm() })
    expect(result.current.state?.kind).toBe('progress')
    act(() => { result.current.cancel() })

    // Upload B: start and confirm. A's promise still in flight.
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'T')
    })
    let confirmB: Promise<void> = Promise.resolve()
    act(() => { confirmB = result.current.confirm() })
    expect(result.current.state?.kind).toBe('progress')
    expect(signalB).toBeDefined()

    // A's promise resolves NOW — its finally would clobber B's controller
    // (set abortCtlRef.current = null) unless guarded.
    await act(async () => {
      resolveA([{ project_id: 'pa', filename: 'a.md', status: 'created' }])
      await confirmA
    })

    // Now cancel B. cancel() reads abortCtlRef.current; if A clobbered it,
    // B's signal is never aborted. Verify B's signal was actually aborted.
    act(() => { result.current.cancel() })
    expect(signalB?.aborted).toBe(true)

    // Clean up B
    await act(async () => {
      resolveB([])
      await confirmB
    })
  })

  it('cancel during upload bails before summary fires', async () => {
    // Reproduces the bug where a late onProgress callback (or the post-upload
    // summary setState) reanimated the modal after the user clicked Cancel.
    const files = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    let resolveUpload: (rows: UploadRow[]) => void = () => {}
    const uploadPromise = new Promise<UploadRow[]>((resolve) => {
      resolveUpload = resolve
    })
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockImplementation(
      async (_batches, _topic, _sid, onProgress) => {
        // Simulate a progress callback firing after cancel — the in-flight
        // batch completes between cancel() and signal.aborted being checked.
        queueMicrotask(() => onProgress(1, 1, 1, 1))
        return uploadPromise
      },
    )

    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'x' }, 'Barsoom')
    })
    expect(result.current.state?.kind).toBe('preflight')

    // Trigger confirm but don't await — keep the upload pending so we can
    // cancel mid-flight before the mocked uploadFolderInBatches resolves.
    let confirmPromise: Promise<void> = Promise.resolve()
    act(() => {
      confirmPromise = result.current.confirm()
    })
    // Cancel while upload is still in flight.
    act(() => {
      result.current.cancel()
    })
    expect(result.current.state).toBeNull()

    // Now resolve the upload to simulate the in-flight batch completing.
    await act(async () => {
      resolveUpload([{ project_id: 'p1', filename: 'a.md', status: 'created' }])
      await confirmPromise
    })

    // The summary must NOT appear: cancel was honoured.
    expect(result.current.state).toBeNull()
  })
})
