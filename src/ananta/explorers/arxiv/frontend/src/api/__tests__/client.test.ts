import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../client'

const mockFetch = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({}),
  })
  vi.stubGlobal('fetch', mockFetch)
})

describe('api.papers.remove', () => {
  it('encodes arxiv IDs that contain slashes', async () => {
    await api.papers.remove('my-topic', 'physics/0203087v2')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/topics/my-topic/papers/physics%2F0203087v2',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
