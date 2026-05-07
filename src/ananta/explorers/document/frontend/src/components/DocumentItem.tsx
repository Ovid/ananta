import type { DocumentItem as DocumentItemType, DocumentInfo } from '../types'

const FILE_ICONS: Record<string, string> = {
  'application/pdf': '\uD83D\uDCC4',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '\uD83D\uDCDD',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '\uD83D\uDCCA',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': '\uD83D\uDCCA',
  'text/plain': '\uD83D\uDCC3',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Converts a DocumentInfo-like object to the DocumentItem format used by TopicSidebar.
 */
export function docToDocumentItem(doc: {
  project_id: string
  filename: string
  content_type: string
  size: number
}): DocumentItemType {
  const icon = FILE_ICONS[doc.content_type] || '\uD83D\uDCC1'
  return {
    id: doc.project_id,
    label: doc.filename,
    sublabel: `${icon} ${formatSize(doc.size)}`,
  }
}

interface DocumentItemProps {
  doc: DocumentInfo
}

/**
 * Renders a single document with its filename and (when present) its
 * relative_path as a subtitle. The relative_path is shown for documents
 * uploaded as part of a folder so the original directory structure is
 * visible in the document list.
 */
export function DocumentItem({ doc }: DocumentItemProps) {
  return (
    <div>
      <div className="text-sm text-text-primary truncate">{doc.filename}</div>
      {doc.relative_path && (
        <div data-testid="relative-path" className="text-xs text-text-dim">
          {doc.relative_path}
        </div>
      )}
    </div>
  )
}
