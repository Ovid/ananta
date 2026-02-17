import { describe, it, expect, vi, beforeEach } from 'vitest'
import { request, sharedApi } from '../client'

const mockFetch = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
  })
  vi.stubGlobal('fetch', mockFetch)
})

describe('request', () => {
  it('makes GET request to /api + path with JSON content-type', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: 'test' }),
    })

    const result = await request<{ data: string }>('/some/path')

    expect(mockFetch).toHaveBeenCalledWith('/api/some/path', {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toEqual({ data: 'test' })
  })

  it('passes options through to fetch', async () => {
    await request('/items', { method: 'POST', body: JSON.stringify({ x: 1 }) })

    expect(mockFetch).toHaveBeenCalledWith('/api/items', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({ x: 1 }),
    })
  })

  it('throws error with detail from JSON error response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ detail: 'Invalid input' }),
    })

    await expect(request('/fail')).rejects.toThrow('Invalid input')
  })

  it('throws error with statusText when JSON parse fails', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new Error('not json')),
    })

    await expect(request('/fail')).rejects.toThrow('Internal Server Error')
  })

  it('throws error with statusText when detail is empty', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
      json: () => Promise.resolve({}),
    })

    await expect(request('/missing')).rejects.toThrow('Not Found')
  })
})

describe('sharedApi.topics', () => {
  it('list fetches /topics', async () => {
    await sharedApi.topics.list()
    expect(mockFetch).toHaveBeenCalledWith('/api/topics', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('create posts name to /topics', async () => {
    await sharedApi.topics.create('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({ name: 'my-topic' }),
    })
  })

  it('rename patches topic with new_name', async () => {
    await sharedApi.topics.rename('old-name', 'new-name')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/old-name', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify({ new_name: 'new-name' }),
    })
  })

  it('rename encodes topic name', async () => {
    await sharedApi.topics.rename('a topic', 'b topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic', expect.any(Object))
  })

  it('delete sends DELETE to /topics/:name', async () => {
    await sharedApi.topics.delete('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })
})

describe('sharedApi.traces', () => {
  it('list fetches traces for topic', async () => {
    await sharedApi.traces.list('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/traces', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('list encodes topic name', async () => {
    await sharedApi.traces.list('a topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic/traces', expect.any(Object))
  })

  it('get fetches specific trace', async () => {
    await sharedApi.traces.get('my-topic', 'trace-123')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/traces/trace-123', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('get encodes traceId', async () => {
    await sharedApi.traces.get('my-topic', 'trace with spaces')
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/topics/my-topic/traces/trace%20with%20spaces',
      expect.any(Object),
    )
  })
})

describe('sharedApi.history', () => {
  it('get fetches history for topic', async () => {
    await sharedApi.history.get('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/history', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('clear sends DELETE to history', async () => {
    await sharedApi.history.clear('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/history', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })

  it('clear encodes topic name', async () => {
    await sharedApi.history.clear('a topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic/history', expect.objectContaining({ method: 'DELETE' }))
  })
})

describe('sharedApi.model', () => {
  it('get fetches /model', async () => {
    await sharedApi.model.get()
    expect(mockFetch).toHaveBeenCalledWith('/api/model', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('update sends PUT with model name', async () => {
    await sharedApi.model.update('gpt-4')
    expect(mockFetch).toHaveBeenCalledWith('/api/model', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PUT',
      body: JSON.stringify({ model: 'gpt-4' }),
    })
  })
})

describe('sharedApi.contextBudget', () => {
  it('fetches context-budget for topic', async () => {
    await sharedApi.contextBudget('my-topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/context-budget', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('encodes topic name', async () => {
    await sharedApi.contextBudget('a topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic/context-budget', expect.any(Object))
  })
})

describe('sharedApi.export', () => {
  it('fetches export as text', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('exported data'),
    })

    const result = await sharedApi.export('my-topic')

    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/export')
    expect(result).toBe('exported data')
  })

  it('encodes topic name', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(''),
    })

    await sharedApi.export('a topic')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/a%20topic/export')
  })

  it('throws when response is not ok', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
      text: () => Promise.resolve(''),
    })

    await expect(sharedApi.export('my-topic')).rejects.toThrow('Not Found')
  })
})
