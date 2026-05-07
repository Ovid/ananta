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

export interface WalkedFile {
  file: File
  relativePath: string
}

// FileSystemEntry / FileSystemDirectoryEntry / FileSystemFileEntry /
// FileSystemDirectoryReader are declared globally in lib.dom.d.ts; we use
// those types directly rather than redeclare them.

function readAllEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = []
    const readBatch = (): void => {
      reader.readEntries(
        (batch) => {
          if (batch.length === 0) {
            resolve(all)
          } else {
            all.push(...batch)
            // Defer recursion so the reader's bookkeeping (e.g., the
            // post-callback "returned" flip in tests, and Safari's internal
            // cursor advance) completes before we ask for the next batch.
            queueMicrotask(readBatch)
          }
        },
        reject,
      )
    }
    readBatch()
  })
}

function getFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

export async function walkEntries(
  entries: FileSystemEntry[],
  rootName: string,
): Promise<WalkedFile[]> {
  // Returns every walked file (allowlist filtering is the hook's job — it
  // re-runs filterFiles to categorise skipped rows for the summary). The cap
  // is enforced on the *accepted* count so a folder of many unsupported files
  // (e.g., a git repo with image assets) doesn't trip the cap before reaching
  // its few supported source files (Inline 5).
  //
  // *rootName* is kept on the call signature for backward-compat callers, but
  // when multiple top-level entries are dropped each subtree's prefix is
  // derived from its own top-level entry (I4) — using a single root for all
  // entries previously left files from secondary folders with an
  // unstripped folder/ prefix.
  void rootName
  const result: WalkedFile[] = []
  let acceptedCount = 0

  const visit = async (entry: FileSystemEntry, stripPrefix: (p: string) => string): Promise<void> => {
    if (entry.isFile) {
      // Per-file errors (permission denied, OS quirks, race with deletion)
      // must not abort the whole walk (I8). Drop the unreadable file and
      // continue so the user still sees the readable ones in the summary.
      let file: File
      try {
        file = await getFile(entry as FileSystemFileEntry)
      } catch {
        return
      }
      const accepted =
        SUPPORTED_EXTENSIONS.includes(getExtension(file.name)) &&
        file.size <= MAX_UPLOAD_BYTES
      if (accepted) {
        if (acceptedCount >= MAX_FOLDER_FILES) {
          throw new Error(`folder exceeds the ${MAX_FOLDER_FILES}-file limit`)
        }
        acceptedCount++
      }
      // Emit every walked file regardless of allowlist so the hook's
      // filterFiles call can categorise the skipped ones for the summary.
      result.push({ file, relativePath: stripPrefix(entry.fullPath) })
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      const children = await readAllEntries(reader)
      for (const child of children) {
        // A failure inside a subtree (e.g. unreadable nested dir) shouldn't
        // throw the whole walk away. The cap-exceeded throw must still
        // propagate, since that signals a hard refusal.
        try {
          await visit(child, stripPrefix)
        } catch (err) {
          if (err instanceof Error && /folder.*limit/i.test(err.message)) throw err
          // else: swallow per-file/per-subtree error and continue
        }
      }
    }
  }

  for (const entry of entries) {
    // Derive a per-entry stripPrefix so each dropped folder loses its OWN
    // top-level name (I4). For top-level files the strip is just the
    // leading slash.
    const ownRoot = entry.isDirectory ? entry.name : ''
    const stripPrefix = ownRoot
      ? (fullPath: string): string => {
          const prefix = `/${ownRoot}/`
          return fullPath.startsWith(prefix)
            ? fullPath.slice(prefix.length)
            : fullPath.replace(/^\//, '')
        }
      : (fullPath: string): string => fullPath.replace(/^\//, '')
    await visit(entry, stripPrefix)
  }
  return result
}

export function partitionIntoBatches(
  files: WalkedFile[],
  targetBytes: number,
): WalkedFile[][] {
  const batches: WalkedFile[][] = []
  let current: WalkedFile[] = []
  let currentBytes = 0
  for (const wf of files) {
    if (current.length > 0 && currentBytes + wf.file.size > targetBytes) {
      batches.push(current)
      current = []
      currentBytes = 0
    }
    current.push(wf)
    currentBytes += wf.file.size
  }
  if (current.length > 0) batches.push(current)
  return batches
}
