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
