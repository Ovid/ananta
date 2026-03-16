import { request, sharedApi } from '@shesha/shared-ui'
import type { DocumentInfo } from '../types'

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
    topics: (id: string) =>
      request<string[]>(`/documents/${encodeURIComponent(id)}/topics`),
    upload: (files: File[], topic?: string) => {
      const formData = new FormData()
      for (const file of files) formData.append('files', file)
      if (topic) formData.append('topic', topic)
      // Override headers to let the browser set Content-Type with boundary for multipart
      return request<{ project_id: string; filename: string; status: string }[]>(
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
