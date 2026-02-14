import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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

afterEach(() => vi.restoreAllMocks())

// Lazy import so the module picks up our stubbed fetch
async function getApi() {
  const mod = await import('../client')
  return mod.api
}

describe('api.repos', () => {
  it('list fetches GET /api/repos', async () => {
    const api = await getApi()
    await api.repos.list()
    expect(mockFetch).toHaveBeenCalledWith('/api/repos', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('add posts JSON body to /api/repos', async () => {
    const api = await getApi()
    await api.repos.add({ url: 'https://github.com/example/repo', topic: 'my-topic' })
    expect(mockFetch).toHaveBeenCalledWith('/api/repos', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({ url: 'https://github.com/example/repo', topic: 'my-topic' }),
    })
  })

  it('get fetches GET /api/repos/{id}', async () => {
    const api = await getApi()
    await api.repos.get('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('get encodes repo id', async () => {
    const api = await getApi()
    await api.repos.get('repo with spaces')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/repo%20with%20spaces', expect.any(Object))
  })

  it('delete sends DELETE to /api/repos/{id}', async () => {
    const api = await getApi()
    await api.repos.delete('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })

  it('checkUpdates sends POST to /api/repos/{id}/check-updates', async () => {
    const api = await getApi()
    await api.repos.checkUpdates('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo/check-updates', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    })
  })

  it('applyUpdates sends POST to /api/repos/{id}/apply-updates', async () => {
    const api = await getApi()
    await api.repos.applyUpdates('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo/apply-updates', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    })
  })

  it('analyze sends POST to /api/repos/{id}/analyze', async () => {
    const api = await getApi()
    await api.repos.analyze('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo/analyze', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    })
  })

  it('getAnalysis fetches GET /api/repos/{id}/analysis', async () => {
    const api = await getApi()
    await api.repos.getAnalysis('my-repo')
    expect(mockFetch).toHaveBeenCalledWith('/api/repos/my-repo/analysis', {
      headers: { 'Content-Type': 'application/json' },
    })
  })
})

describe('api.topicRepos', () => {
  it('add sends POST to /api/topics/{name}/repos/{projectId}', async () => {
    const api = await getApi()
    await api.topicRepos.add('my-topic', 'proj-123')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/repos/proj-123', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    })
  })

  it('add encodes topic and projectId', async () => {
    const api = await getApi()
    await api.topicRepos.add('a topic', 'proj id')
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/topics/a%20topic/repos/proj%20id',
      expect.any(Object),
    )
  })

  it('remove sends DELETE to /api/topics/{name}/repos/{projectId}', async () => {
    const api = await getApi()
    await api.topicRepos.remove('my-topic', 'proj-123')
    expect(mockFetch).toHaveBeenCalledWith('/api/topics/my-topic/repos/proj-123', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })
})

describe('api.history', () => {
  it('get fetches GET /api/history (global, no topic param)', async () => {
    const api = await getApi()
    await api.history.get()
    expect(mockFetch).toHaveBeenCalledWith('/api/history', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('clear sends DELETE to /api/history (global)', async () => {
    const api = await getApi()
    await api.history.clear()
    expect(mockFetch).toHaveBeenCalledWith('/api/history', {
      headers: { 'Content-Type': 'application/json' },
      method: 'DELETE',
    })
  })
})

describe('api.export', () => {
  it('fetches GET /api/export and returns text', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('exported markdown'),
    })

    const api = await getApi()
    const result = await api.export()

    expect(mockFetch).toHaveBeenCalledWith('/api/export')
    expect(result).toBe('exported markdown')
  })

  it('throws when response is not ok', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
      text: () => Promise.resolve(''),
    })

    const api = await getApi()
    await expect(api.export()).rejects.toThrow('Not Found')
  })
})

describe('api inherits shared methods', () => {
  it('has topics from shared api', async () => {
    const api = await getApi()
    expect(api.topics).toBeDefined()
    expect(typeof api.topics.list).toBe('function')
    expect(typeof api.topics.create).toBe('function')
    expect(typeof api.topics.rename).toBe('function')
    expect(typeof api.topics.delete).toBe('function')
  })

  it('has traces from shared api', async () => {
    const api = await getApi()
    expect(api.traces).toBeDefined()
    expect(typeof api.traces.list).toBe('function')
    expect(typeof api.traces.get).toBe('function')
  })

  it('has model from shared api', async () => {
    const api = await getApi()
    expect(api.model).toBeDefined()
    expect(typeof api.model.get).toBe('function')
    expect(typeof api.model.update).toBe('function')
  })

  it('has contextBudget from shared api', async () => {
    const api = await getApi()
    expect(typeof api.contextBudget).toBe('function')
  })
})
