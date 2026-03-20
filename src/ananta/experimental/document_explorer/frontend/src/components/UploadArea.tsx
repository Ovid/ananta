import { useState, useRef, useCallback, type DragEvent, type KeyboardEvent } from 'react'

interface UploadAreaProps {
  onUpload: (files: File[]) => Promise<void>
}

export default function UploadArea({ onUpload }: UploadAreaProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

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
    await handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload files"
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      className={`mx-2 mb-2 p-3 border border-dashed rounded-lg text-center cursor-pointer transition-colors text-xs ${
        dragging
          ? 'border-accent bg-accent-dim text-accent'
          : 'border-border text-text-dim hover:border-text-dim hover:text-text-secondary'
      } ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={async e => { if (e.target.files) await handleFiles(e.target.files) }}
      />
      {uploading ? 'Uploading...' : 'Drop files here or click to upload'}
    </div>
  )
}
