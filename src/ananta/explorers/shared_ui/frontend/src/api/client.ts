import type { TopicInfo, TraceListItem, TraceFull, Exchange, ContextBudget, ModelInfo } from '../types'

const BASE = '/api'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || resp.statusText)
  }
  return resp.json()
}

export const sharedApi = {
  topics: {
    list: () => request<TopicInfo[]>('/topics'),
    create: (name: string) => request<{ name: string; project_id: string }>('/topics', {
      method: 'POST', body: JSON.stringify({ name }),
    }),
    rename: (name: string, newName: string) => request<{ name: string }>(`/topics/${encodeURIComponent(name)}`, {
      method: 'PATCH', body: JSON.stringify({ new_name: newName }),
    }),
    delete: (name: string) => request<void>(`/topics/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    reorderItems: (name: string, itemIds: string[]) => request<{ status: string }>(
      `/topics/${encodeURIComponent(name)}/items/order`,
      { method: 'PUT', body: JSON.stringify({ item_ids: itemIds }) },
    ),
  },
  traces: {
    list: (topic: string) => request<TraceListItem[]>(
      `/topics/${encodeURIComponent(topic)}/traces`,
    ),
    get: (topic: string, traceId: string) => request<TraceFull>(
      `/topics/${encodeURIComponent(topic)}/traces/${encodeURIComponent(traceId)}`,
    ),
    download: async (topic: string, traceId: string) => {
      const resp = await fetch(`${BASE}/topics/${encodeURIComponent(topic)}/trace-download/${encodeURIComponent(traceId)}`)
      if (!resp.ok) throw new Error(resp.statusText)
      const blob = await resp.blob()
      const disposition = resp.headers.get('content-disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `${traceId}.jsonl`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
  },
  history: {
    get: (topic: string) => request<{ exchanges: Exchange[] }>(`/topics/${encodeURIComponent(topic)}/history`),
    clear: (topic: string) => request<void>(`/topics/${encodeURIComponent(topic)}/history`, { method: 'DELETE' }),
  },
  export: (topic: string) => fetch(`${BASE}/topics/${encodeURIComponent(topic)}/export`).then(r => {
    if (!r.ok) throw new Error(r.statusText)
    return r.text()
  }),
  model: {
    get: () => request<ModelInfo>('/model'),
    update: (model: string) => request<ModelInfo>('/model', {
      method: 'PUT', body: JSON.stringify({ model }),
    }),
  },
  contextBudget: (topic: string) => request<ContextBudget>(
    `/topics/${encodeURIComponent(topic)}/context-budget`,
  ),
}
