import type { DocumentItem } from '../types'

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
}): DocumentItem {
  const icon = FILE_ICONS[doc.content_type] || '\uD83D\uDCC1'
  return {
    id: doc.project_id,
    label: doc.filename,
    sublabel: `${icon} ${formatSize(doc.size)}`,
  }
}
