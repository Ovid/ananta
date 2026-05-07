import { request, sharedApi } from '@ananta/shared-ui'
import type { DocumentInfo } from '../types'
import type { UploadRow } from './documents'

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
    upload: (files: File[], topic?: string) => {
      const formData = new FormData()
      for (const file of files) {
        formData.append('files', file)
        // Append a relative_path entry per file so click-folder selections
        // and multi-select drops in a subdirectory keep their webkit path
        // (I13). Empty string means "no relative path" and is normalised
        // to None server-side. The backend requires the array length to
        // match files.length once any value is supplied.
        formData.append('relative_path', file.webkitRelativePath ?? '')
      }
      if (topic) formData.append('topic', topic)
      // Override headers to let the browser set Content-Type with boundary for multipart
      return request<UploadRow[]>(
        '/documents/upload',
        { method: 'POST', body: formData, headers: {} },
      )
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
