import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the hooks that useAppState depends on
const mockSend = vi.fn()
const mockOnMessage = vi.fn()
const mockToggleTheme = vi.fn()

vi.mock('../useWebSocket', () => ({
  useWebSocket: () => ({
    connected: true,
    send: mockSend,
    onMessage: mockOnMessage,
  }),
}))

vi.mock('../useTheme', () => ({
  useTheme: () => ({
    dark: true,
    toggle: mockToggleTheme,
  }),
}))

// Mock fetch for model loading
vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ model: 'test-model', max_input_tokens: 128000 }),
}))

import { useAppState } from '../useAppState'

/** Helper: render the hook and wait for the async model-fetch to settle. */
async function renderAppState(options?: Parameters<typeof useAppState>[0]) {
  const hook = renderHook(() => useAppState(options))
  // Wait for the model.get() promise chain to resolve and update state
  await waitFor(() => {
    expect(hook.result.current.modelName).toBe('test-model')
  })
  return hook
}

describe('useAppState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockOnMessage.mockReturnValue(() => {})
  })

  it('provides initial state', async () => {
    const { result } = await renderAppState()
    expect(result.current.dark).toBe(true)
    expect(result.current.connected).toBe(true)
    expect(result.current.phase).toBe('Ready')
    expect(result.current.activeTopic).toBeNull()
    expect(result.current.sidebarWidth).toBe(224)
    expect(result.current.traceView).toBeNull()
    expect(result.current.historyVersion).toBe(0)
    expect(result.current.modelName).toBe('test-model')
  })

  it('registers WebSocket message listener', async () => {
    await renderAppState()
    expect(mockOnMessage).toHaveBeenCalledWith(expect.any(Function))
  })

  it('updates phase on status message', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({ type: 'status', phase: 'Querying' })
    })
    expect(result.current.phase).toBe('Querying')
  })

  it('resets phase on complete message', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({
        type: 'complete',
        answer: 'done',
        trace_id: 't1',
        tokens: { prompt: 10, completion: 5, total: 15 },
        duration_ms: 100,
      })
    })
    expect(result.current.phase).toBe('Ready')
    expect(result.current.tokens).toEqual({ prompt: 10, completion: 5, total: 15 })
  })

  it('calls onComplete callback after complete message', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const onComplete = vi.fn()
    await renderAppState({ onComplete })
    act(() => {
      messageHandler({
        type: 'complete',
        answer: 'done',
        trace_id: null,
        tokens: { prompt: 1, completion: 1, total: 2 },
        duration_ms: 50,
      })
    })
    expect(onComplete).toHaveBeenCalled()
  })

  it('forwards unknown messages to onExtraMessage', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const onExtraMessage = vi.fn()
    await renderAppState({ onExtraMessage })
    act(() => {
      messageHandler({ type: 'citation_progress', current: 1, total: 3 })
    })
    expect(onExtraMessage).toHaveBeenCalledWith({ type: 'citation_progress', current: 1, total: 3 })
  })

  it('delegates error to onExtraMessage when provided', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const onExtraMessage = vi.fn()
    await renderAppState({ onExtraMessage })
    act(() => {
      messageHandler({ type: 'error', message: 'Something failed' })
    })
    expect(onExtraMessage).toHaveBeenCalledWith({ type: 'error', message: 'Something failed' })
  })

  it('sets phase to Error when no onExtraMessage for error', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({ type: 'error', message: 'Something failed' })
    })
    expect(result.current.phase).toBe('Error')
  })

  it('handles step message with tokens', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({
        type: 'step',
        step_type: 'code',
        iteration: 3,
        content: 'print(1)',
        prompt_tokens: 500,
        completion_tokens: 100,
      })
    })
    expect(result.current.phase).toBe('code (iter 3)')
    expect(result.current.tokens).toEqual({ prompt: 500, completion: 100, total: 600 })
  })

  it('resets phase on cancelled message', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({ type: 'status', phase: 'Running' })
    })
    expect(result.current.phase).toBe('Running')

    act(() => {
      messageHandler({ type: 'cancelled' })
    })
    expect(result.current.phase).toBe('Ready')
  })

  it('sets document_bytes from complete message', async () => {
    let messageHandler: (msg: any) => void = () => {}
    mockOnMessage.mockImplementation((fn: any) => {
      messageHandler = fn
      return () => {}
    })

    const { result } = await renderAppState()
    act(() => {
      messageHandler({
        type: 'complete',
        answer: 'done',
        trace_id: 't1',
        tokens: { prompt: 10, completion: 5, total: 15 },
        duration_ms: 100,
        document_bytes: 4096,
      })
    })
    expect(result.current.documentBytes).toBe(4096)
  })

  it('handleSidebarDrag creates mouse listeners', async () => {
    const addListener = vi.spyOn(document, 'addEventListener')
    const { result } = await renderAppState()
    act(() => {
      result.current.handleSidebarDrag({
        preventDefault: vi.fn(),
        clientX: 100,
      } as any)
    })
    expect(addListener).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(addListener).toHaveBeenCalledWith('mouseup', expect.any(Function))
    addListener.mockRestore()
  })

  it('handleTopicSelect sets activeTopic', async () => {
    const { result } = await renderAppState()
    await act(async () => {
      result.current.handleTopicSelect('my-topic')
    })
    expect(result.current.activeTopic).toBe('my-topic')
  })

  it('handleViewTrace sets traceView with current activeTopic', async () => {
    const { result } = await renderAppState()
    await act(async () => {
      result.current.handleTopicSelect('my-topic')
    })
    act(() => {
      result.current.handleViewTrace('trace-123')
    })
    expect(result.current.traceView).toEqual({ topic: 'my-topic', traceId: 'trace-123' })
  })

  it('exposes setters for state that consumers may need to update', async () => {
    const { result } = await renderAppState()
    expect(typeof result.current.setActiveTopic).toBe('function')
    expect(typeof result.current.setPhase).toBe('function')
    expect(typeof result.current.setBudget).toBe('function')
    expect(typeof result.current.setTokens).toBe('function')
    expect(typeof result.current.setHistoryVersion).toBe('function')
    expect(typeof result.current.setTraceView).toBe('function')
  })
})
