// Mirror of src/ananta/explorers/document/config.py.
// Keep these in sync with the backend; config.py is the source of truth.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024
export const MAX_AGGREGATE_UPLOAD_BYTES = 200 * 1024 * 1024
export const MAX_FOLDER_FILES = 500
export const SOFT_WARN_FOLDER_FILES = 100
export const TARGET_BATCH_BYTES = 50 * 1024 * 1024

// Mirror of src/ananta/explorers/document/extractors.py supported list.
export const SUPPORTED_EXTENSIONS: readonly string[] = [
  '.txt', '.md', '.csv', '.log', '.json', '.yaml', '.yml', '.xml', '.html',
  '.htm', '.ini', '.cfg', '.toml', '.env', '.py', '.js', '.ts', '.java',
  '.c', '.cpp', '.h', '.rs', '.go', '.rb', '.sh', '.bat', '.sql', '.r',
  '.tex', '.pdf', '.docx', '.pptx', '.xlsx', '.rtf',
] as const

export interface SkippedFile {
  file: File
  reason: string
}

export interface FilterResult {
  accepted: File[]
  skipped: SkippedFile[]
}

function getExtension(name: string): string {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i).toLowerCase()
}

const OVERSIZE_REASON = `file exceeds ${MAX_UPLOAD_BYTES / 1024 / 1024} MB limit`

export function filterFiles(files: File[]): FilterResult {
  const accepted: File[] = []
  const skipped: SkippedFile[] = []
  for (const file of files) {
    if (!SUPPORTED_EXTENSIONS.includes(getExtension(file.name))) {
      skipped.push({ file, reason: 'unsupported extension' })
    } else if (file.size > MAX_UPLOAD_BYTES) {
      skipped.push({ file, reason: OVERSIZE_REASON })
    } else {
      accepted.push(file)
    }
  }
  return { accepted, skipped }
}
