import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../useWebSocket'

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  readyState = 0
  closed = false

  url: string
  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()
  close() {
    this.closed = true
    this.readyState = 3
    this.onclose?.()
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('does not reconnect after unmount', () => {
    const { unmount } = renderHook(() => useWebSocket())

    // WebSocket connected
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    // Unmount triggers close -> onclose -> setTimeout(connect, 2000)
    unmount()

    // Advance past the reconnect delay
    act(() => vi.advanceTimersByTime(3000))

    // Should NOT have created a second WebSocket
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('reconnects while mounted', () => {
    renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    // Simulate server-side close while still mounted
    act(() => ws.close())

    // Advance past the reconnect delay
    act(() => vi.advanceTimersByTime(3000))

    // Should have created a second WebSocket for reconnection
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('does not re-render host component on every message', () => {
    let renderCount = 0
    const { result } = renderHook(() => {
      renderCount++
      return useWebSocket()
    })

    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())
    const rendersAfterOpen = renderCount

    // Send 5 messages — should NOT cause re-renders
    for (let i = 0; i < 5; i++) {
      act(() => ws.onmessage?.({ data: JSON.stringify({ type: 'status', phase: `Step ${i}` }) }))
    }

    // Listeners should still be notified
    const listener = vi.fn()
    act(() => { result.current.onMessage(listener) })
    act(() => ws.onmessage?.({ data: JSON.stringify({ type: 'status', phase: 'test' }) }))
    expect(listener).toHaveBeenCalled()

    // But render count should not have increased from the 5 messages
    // (only the listener registration might cause a render)
    expect(renderCount).toBeLessThanOrEqual(rendersAfterOpen + 1)
  })
})
