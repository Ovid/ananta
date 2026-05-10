import type { DocumentItem as DocumentItemType } from '../types'

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
 *
 * - `sublabel` is the hover-tooltip (size + icon).
 * - `subtitle` is rendered as a visible second line under the label and carries
 *   `relative_path` for documents uploaded as part of a folder, so the original
 *   directory structure is visible in the sidebar.
 */
export function docToDocumentItem(doc: {
  project_id: string
  filename: string
  content_type: string
  size: number
  relative_path?: string | null
}): DocumentItemType {
  // Strip parameter suffixes ("; charset=utf-8", "; boundary=...") before
  // the lookup. Browsers may include them and the backend stores
  // ``UploadFile.content_type`` verbatim, so an exact-match table missed
  // legitimate "text/plain; charset=utf-8" entries (S37).
  const baseType = doc.content_type.split(';', 1)[0].trim()
  const icon = FILE_ICONS[baseType] || '\uD83D\uDCC1'
  const item: DocumentItemType = {
    id: doc.project_id,
    label: doc.filename,
    sublabel: `${icon} ${formatSize(doc.size)}`,
  }
  // Only render the path subtitle when it adds information. For root-level
  // folder uploads the server echoes relative_path == filename, in which case
  // the subtitle would just duplicate the label on a second line.
  if (doc.relative_path && doc.relative_path !== doc.filename) {
    item.subtitle = doc.relative_path
  }
  return item
}
