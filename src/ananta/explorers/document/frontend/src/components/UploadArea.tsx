import { useState, useRef, useCallback, type ChangeEvent, type DragEvent, type KeyboardEvent } from 'react'
import type { WalkedFile } from '../lib/folder-walk'

// Discriminated union: drop path emits FileSystemEntry[] (needs async traversal),
// click path emits WalkedFile[] directly (browser flattens via webkitRelativePath).
// The D2 hook is the seam where both paths converge.
export type FolderUploadInput =
  | { kind: 'entries'; entries: FileSystemEntry[]; rootName: string }
  | { kind: 'walked'; files: WalkedFile[]; rootName: string }

interface FileWithPath extends File {
  webkitRelativePath: string
}

interface UploadAreaProps {
  onUpload: (files: File[]) => Promise<void>
  onFolderUpload?: (input: FolderUploadInput) => Promise<void>
  activeTopic: string | null
}

export default function UploadArea({ onUpload, onFolderUpload, activeTopic }: UploadAreaProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const disabled = activeTopic === null

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files)
    if (fileArray.length === 0) return
    setUploading(true)
    try {
      await onUpload(fileArray)
    } finally {
      setUploading(false)
    }
  }, [onUpload])

  const handleDrop = useCallback(async (e: DragEvent<HTMLDivElement>) => {
    // Always preventDefault, even when disabled: otherwise the browser's
    // default action for a file drop is to navigate to / open the file,
    // blowing away the page state. setDragging(false) is also unconditional
    // so the drop-target highlight clears even when the drop is rejected.
    e.preventDefault()
    setDragging(false)
    if (disabled) return

    const items = Array.from(e.dataTransfer.items ?? [])
    const entries: FileSystemEntry[] = []
    let rootName = ''
    for (const item of items) {
      const entry = (item as DataTransferItem & { webkitGetAsEntry: () => FileSystemEntry | null }).webkitGetAsEntry()
      if (entry) {
        entries.push(entry)
        if (entry.isDirectory && !rootName) rootName = entry.name
      }
    }

    const hasDirectory = entries.some(e => e.isDirectory)
    if (hasDirectory && onFolderUpload) {
      await onFolderUpload({ kind: 'entries', entries, rootName })
    } else {
      await handleFiles(e.dataTransfer.files)
    }
  }, [disabled, handleFiles, onFolderUpload])

  const handleFolderInputChange = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const input = e.target
    const files = Array.from(input.files ?? []) as FileWithPath[]
    // Reset the input value so re-picking the same folder fires change again.
    // Browsers won't fire change when the value is unchanged. Reset before
    // dispatching the upload so failure paths still leave the input usable.
    input.value = ''
    if (files.length === 0 || !onFolderUpload) return
    const firstPath = files[0].webkitRelativePath
    const rootName = firstPath.split('/')[0] ?? ''
    const walked: WalkedFile[] = files.map((f) => {
      const wp = f.webkitRelativePath
      const relativePath = wp.startsWith(`${rootName}/`) ? wp.slice(rootName.length + 1) : wp
      return { file: f, relativePath }
    })
    await onFolderUpload({ kind: 'walked', files: walked, rootName })
  }, [onFolderUpload])

  // Drag/drop handlers are always attached, even when disabled, so the
  // browser doesn't fall back to its default "navigate to dropped file"
  // behaviour. The handlers themselves no-op when disabled.
  const handlers = {
    onDragOver: (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      if (!disabled) setDragging(true)
    },
    onDragLeave: () => setDragging(false),
    onDrop: handleDrop,
    ...(disabled
      ? {}
      : {
          onClick: () => inputRef.current?.click(),
          onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              inputRef.current?.click()
            }
          },
        }),
  }

  return (
    <div className="mx-2 mb-2">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload files"
        aria-disabled={disabled || undefined}
        {...handlers}
        className={`p-3 border border-dashed rounded-lg text-center transition-colors text-xs ${
          disabled
            ? 'border-border text-text-dim opacity-50 cursor-not-allowed'
            : dragging
              ? 'border-accent bg-accent-dim text-accent cursor-pointer'
              : 'border-border text-text-dim hover:border-text-dim hover:text-text-secondary cursor-pointer'
        } ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={async e => { if (e.target.files) await handleFiles(e.target.files) }}
        />
        {disabled
          ? 'Select a topic first'
          : (uploading ? 'Uploading...' : 'Drop files here or click to upload')}
      </div>
      {!disabled && onFolderUpload && (
        <button
          type="button"
          onClick={() => folderInputRef.current?.click()}
          aria-label="Upload folder"
          className="mt-2 w-full px-3 py-1.5 text-xs border border-border rounded-lg text-text-dim hover:border-text-dim hover:text-text-secondary transition-colors cursor-pointer"
        >
          Upload folder
        </button>
      )}
      <input
        ref={folderInputRef}
        type="file"
        // @ts-expect-error - webkitdirectory is not in standard TS DOM types
        webkitdirectory=""
        className="hidden"
        aria-label="folder picker"
        onChange={handleFolderInputChange}
      />
    </div>
  )
}
