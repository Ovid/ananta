import { request, sharedApi } from '@shesha/shared-ui'

import type { RepoInfo, RepoAnalysis, UpdateStatus } from '../types'

export const api = {
  ...sharedApi,

  repos: {
    list: () => request<RepoInfo[]>('/repos'),
    listUncategorized: () => request<RepoInfo[]>('/repos/uncategorized'),
    listForTopic: (topic: string) =>
      request<RepoInfo[]>(`/topics/${encodeURIComponent(topic)}/items`),
    add: (data: { url: string; topic?: string }) =>
      request<{ project_id: string; status: string; files_ingested: number }>('/repos', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    get: (id: string) => request<RepoInfo>(`/repos/${encodeURIComponent(id)}`),
    delete: (id: string) =>
      request<{ status: string; project_id: string }>(`/repos/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      }),
    checkUpdates: (id: string) =>
      request<UpdateStatus>(`/repos/${encodeURIComponent(id)}/check-updates`, {
        method: 'POST',
      }),
    applyUpdates: (id: string) =>
      request<UpdateStatus>(`/repos/${encodeURIComponent(id)}/apply-updates`, {
        method: 'POST',
      }),
    analyze: (id: string) =>
      request<RepoAnalysis>(`/repos/${encodeURIComponent(id)}/analyze`, {
        method: 'POST',
      }),
    getAnalysis: (id: string) =>
      request<RepoAnalysis>(`/repos/${encodeURIComponent(id)}/analysis`),
  },

  topicRepos: {
    add: (topic: string, projectId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(projectId)}`,
        { method: 'POST' },
      ),
    remove: (topic: string, projectId: string) =>
      request<{ status: string }>(
        `/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(projectId)}`,
        { method: 'DELETE' },
      ),
  },
}
