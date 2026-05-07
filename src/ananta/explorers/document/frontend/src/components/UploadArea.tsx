import { useState, useRef, useCallback, type DragEvent, type KeyboardEvent } from 'react'

interface UploadAreaProps {
  onUpload: (files: File[]) => Promise<void>
  onFolderUpload?: (entries: FileSystemEntry[], rootName: string) => Promise<void>
  activeTopic: string | null
}

export default function UploadArea({ onUpload, onFolderUpload, activeTopic }: UploadAreaProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
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
      await onFolderUpload(entries, rootName)
    } else {
      await handleFiles(e.dataTransfer.files)
    }
  }, [disabled, handleFiles, onFolderUpload])

  const handlers = disabled
    ? {}
    : {
        onDragOver: (e: DragEvent<HTMLDivElement>) => { e.preventDefault(); setDragging(true) },
        onDragLeave: () => setDragging(false),
        onDrop: handleDrop,
        onClick: () => inputRef.current?.click(),
        onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        },
      }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload files"
      aria-disabled={disabled || undefined}
      {...handlers}
      className={`mx-2 mb-2 p-3 border border-dashed rounded-lg text-center transition-colors text-xs ${
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
  )
}
