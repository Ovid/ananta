import { request, sharedApi } from '@ananta/shared-ui'
import type { DocumentInfo } from '../types'
import { formatHttpError, type UploadRow } from './documents'

export type { UploadRow }

export const api = {
  ...sharedApi,

  documents: {
    list: () => request<DocumentInfo[]>('/documents'),
    listUncategorized: () => request<DocumentInfo[]>('/documents/uncategorized'),
    listForTopic: (topic: string) =>
      request<DocumentInfo[]>(`/topics/${encodeURIComponent(topic)}/items`),
    get: (id: string) => request<DocumentInfo>(`/documents/${encodeURIComponent(id)}`),
    delete: (id: string) =>
      request<{ status: string }>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    rename: (id: string, newName: string) =>
      request<DocumentInfo>(`/documents/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify({ new_name: newName }),
      }),
    topics: (id: string) =>
      request<string[]>(`/documents/${encodeURIComponent(id)}/topics`),
    upload: async (files: File[], topic?: string): Promise<UploadRow[]> => {
      const formData = new FormData()
      for (const file of files) formData.append('files', file)

      // ``webkitRelativePath`` is undefined in some webviews / non-browser
      // shims and an empty string for click-picked single files. Coalesce
      // missing values to '' so ``FormData.append`` cannot stringify
      // ``undefined`` to the literal string "undefined" — which would then
      // pass server-side validation and persist as a real (bogus) path.
      // Only attach the field at all when at least one file actually carries
      // a relative path; the backend interprets a missing field as "no
      // relative_path supplied" rather than running the length-equality
      // check (U1, I13).
      const paths = files.map(f =>
        typeof f.webkitRelativePath === 'string' ? f.webkitRelativePath : '',
      )
      if (paths.some(p => p !== '')) {
        for (const p of paths) formData.append('relative_path', p)
      }

      if (topic) formData.append('topic', topic)

      // Direct fetch (rather than the shared ``request`` helper) so that
      // a non-OK response is rendered through ``formatHttpError`` — the
      // same friendly mapping the folder-upload path uses (I4). The shared
      // helper does ``new Error(err.detail)``, which stringifies a 422
      // array detail as ``[object Object]``.
      const res = await fetch('/api/documents/upload', { method: 'POST', body: formData })
      if (!res.ok) throw new Error(await formatHttpError(res))
      return (await res.json()) as UploadRow[]
    },
  },

  topicDocs: {
    add: (topic: string, docId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(docId)}`,
        { method: 'POST' },
      ),
    remove: (topic: string, docId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(docId)}`,
        { method: 'DELETE' },
      ),
  },
}
