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

  it('rejects a second concurrent drop while the first walk is in flight (I10)', async () => {
    // The original abortCtl-based guard only blocked re-entry once
    // confirm() set the controller. During the (potentially slow)
    // walkEntries phase, abortCtl was still null and a second drop could
    // clobber state/pending. With the walkingRef guard, the second start()
    // must be a no-op until the first walk releases.
    let resolveFirstFile: ((f: File) => void) | null = null
    // FakeEntry whose .file() callback is held until we resolve it
    // explicitly — pins the first walk in mid-flight.
    const slowFile = {
      isFile: true,
      isDirectory: false,
      name: 'a.md',
      fullPath: '/A/a.md',
      file: (cb: (f: File) => void) => {
        resolveFirstFile = cb
      },
    }
    const slowRoot = {
      isFile: false,
      isDirectory: true,
      name: 'A',
      fullPath: '/A',
      createReader: () => {
        let r = false
        return {
          readEntries: (cb: (entries: unknown[]) => void) => {
            cb(r ? [] : [slowFile])
            r = true
          },
        }
      },
    }
    const fastFile = {
      isFile: true,
      isDirectory: false,
      name: 'b.md',
      fullPath: '/B/b.md',
      file: (cb: (f: File) => void) => cb(new File(['y'], 'b.md')),
    }
    const fastRoot = {
      isFile: false,
      isDirectory: true,
      name: 'B',
      fullPath: '/B',
      createReader: () => {
        let r = false
        return {
          readEntries: (cb: (entries: unknown[]) => void) => {
            cb(r ? [] : [fastFile])
            r = true
          },
        }
      },
    }
    const { result } = renderHook(() => useFolderUpload())
    let firstPromise: Promise<void> | null = null
    let secondPromise: Promise<void> | null = null
    await act(async () => {
      firstPromise = result.current.start(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { kind: 'entries', entries: [slowRoot as any], rootName: 'A' },
        'T',
      )
      // Yield once so the first start() runs up to its await on slowFile.
      await Promise.resolve()
      secondPromise = result.current.start(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { kind: 'entries', entries: [fastRoot as any], rootName: 'B' },
        'T',
      )
      // Second call must return synchronously (it's a no-op via walkingRef).
      await secondPromise
      // Now release the first walk so it can finish.
      resolveFirstFile?.(new File(['x'], 'a.md'))
      await firstPromise
    })
    expect(result.current.state?.kind).toBe('preflight')
    if (result.current.state?.kind === 'preflight') {
      // First walk wins — the accepted list has A's file, not B's.
      expect(result.current.state.accepted.map((w) => w.file.name)).toEqual(['a.md'])
    }
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

  it('summary disambiguates duplicate-named skipped/failed files by relative path (I4)', async () => {
    // Two README.md files in different subdirectories must not present
    // identically in the summary's skipped or failed lists. The summary
    // takes its display name from relativePath / relative_path when it
    // differs from the bare filename, so the user can tell which copy
    // is which.
    const files = [
      { file: new File([''], 'README.md'), relativePath: 'pkg-a/README.md' },
      { file: new File([''], 'README.md'), relativePath: 'pkg-b/README.md' },
      { file: new File([''], 'logo.png'), relativePath: 'pkg-a/logo.png' },
      { file: new File([''], 'logo.png'), relativePath: 'pkg-b/logo.png' },
    ]
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockResolvedValue([
      {
        project_id: '',
        filename: 'README.md',
        status: 'failed',
        reason: 'unexpected upload error',
        relative_path: 'pkg-a/README.md',
      },
      {
        project_id: 'p2',
        filename: 'README.md',
        status: 'created',
        relative_path: 'pkg-b/README.md',
      },
    ])
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'pkgs' }, 'T')
    })
    await act(async () => {
      await result.current.confirm()
    })
    expect(result.current.state?.kind).toBe('summary')
    if (result.current.state?.kind === 'summary') {
      // Failed row: the path-disambiguated name, not bare 'README.md'.
      expect(result.current.state.failed).toEqual([
        { name: 'pkg-a/README.md', reason: 'unexpected upload error' },
      ])
      // Skipped rows: each logo.png keeps its own subfolder prefix.
      const skippedNames = result.current.state.skipped.map((s) => s.name).sort()
      expect(skippedNames).toEqual(['pkg-a/logo.png', 'pkg-b/logo.png'])
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

  it('walked path counts the cap on accepted files only (I7)', async () => {
    // Reproduces I7: click-folder previously checked raw input.files.length
    // against MAX_FOLDER_FILES, while drag-drop's walkEntries counted only
    // the *accepted* (allowlisted) files. A folder with 1 supported file
    // and 600 PNGs succeeded via drop but failed via click. Align: the
    // walked path also counts the accepted set.
    const supported = [{ file: new File(['x'], 'note.md'), relativePath: 'note.md' }]
    const unsupported = Array.from({ length: 600 }, (_, i) => ({
      file: new File(['x'], `img${i}.png`),
      relativePath: `img${i}.png`,
    }))
    const files = [...supported, ...unsupported]
    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files, rootName: 'mixed' }, 'Barsoom')
    })
    // Should reach preflight (NOT summary), because only 1 supported file
    // counts against the cap.
    expect(result.current.state?.kind).toBe('preflight')
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

  it('start is a no-op while a previous upload is still in flight (I9)', async () => {
    // Reproduces I9: a second drop while the first upload is in flight
    // previously clobbered state and pending. The first upload's progress
    // callback then re-overwrote state to its own progress, churning the
    // modal. Fix: start() refuses if abortCtlRef.current is non-null.
    const filesA = [{ file: new File(['x'], 'a.md'), relativePath: 'a.md' }]
    const filesB = [{ file: new File(['y'], 'b.md'), relativePath: 'b.md' }]
    let resolveA: (rows: UploadRow[]) => void = () => {}
    const promiseA = new Promise<UploadRow[]>((r) => { resolveA = r })
    vi.spyOn(documentsApi, 'uploadFolderInBatches').mockImplementation(async () => promiseA)

    const { result } = renderHook(() => useFolderUpload())
    await act(async () => {
      await result.current.start({ kind: 'walked', files: filesA, rootName: 'a' }, 'T')
    })
    let confirmA: Promise<void> = Promise.resolve()
    act(() => { confirmA = result.current.confirm() })
    expect(result.current.state?.kind).toBe('progress')

    const stateBefore = result.current.state
    // Second start() while A is in flight — must NOT overwrite state.
    await act(async () => {
      await result.current.start({ kind: 'walked', files: filesB, rootName: 'b' }, 'T')
    })
    expect(result.current.state).toBe(stateBefore)

    await act(async () => {
      resolveA([{ project_id: 'p', filename: 'a.md', status: 'created' }])
      await confirmA
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
