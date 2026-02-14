import { request, sharedApi } from '@shesha/shared-ui'
import type { TopicInfo, PaperInfo, SearchResult, Exchange } from '../types'

export const api = {
  ...sharedApi,
  // Override topics.list to return arxiv TopicInfo (with paper_count instead of document_count)
  topics: {
    ...sharedApi.topics,
    list: () => request<TopicInfo[]>('/topics'),
  },
  // Override history.get to return arxiv Exchange (with paper_ids instead of document_ids)
  history: {
    ...sharedApi.history,
    get: (topic: string) => request<{ exchanges: Exchange[] }>(`/topics/${encodeURIComponent(topic)}/history`),
  },
  // Arxiv-specific: paper management
  papers: {
    list: (topic: string) => request<PaperInfo[]>(`/topics/${encodeURIComponent(topic)}/papers`),
    add: (arxivId: string, topics: string[]) => request<{ task_id?: string }>('/papers/add', {
      method: 'POST', body: JSON.stringify({ arxiv_id: arxivId, topics }),
    }),
    remove: (topic: string, arxivId: string) => request<void>(
      `/topics/${encodeURIComponent(topic)}/papers/${encodeURIComponent(arxivId)}`, { method: 'DELETE' },
    ),
    taskStatus: (taskId: string) => request<{ task_id: string; papers: { arxiv_id: string; status: string }[] }>(
      `/papers/tasks/${taskId}`,
    ),
    search: (q: string) => request<SearchResult[]>(`/papers/search?q=${encodeURIComponent(q)}`),
  },
  // Arxiv-specific: arxiv search
  search: (params: { q: string; author?: string; category?: string; sort_by?: string; start?: number }) => {
    const qs = new URLSearchParams()
    qs.set('q', params.q)
    if (params.author) qs.set('author', params.author)
    if (params.category) qs.set('category', params.category)
    if (params.sort_by) qs.set('sort_by', params.sort_by)
    if (params.start) qs.set('start', String(params.start))
    return request<SearchResult[]>(`/search?${qs}`)
  },
}
