import { useEffect, useRef, useCallback, useState } from 'react'
import type { WSMessage } from '../types'

export function useWebSocket<M extends WSMessage = WSMessage>() {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const listenersRef = useRef<((msg: M) => void)[]>([])

  useEffect(() => {
    let unmounted = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`)

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, 2000)
        }
      }
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as M
        listenersRef.current.forEach(fn => fn(msg))
      }

      wsRef.current = ws
    }

    connect()

    return () => {
      unmounted = true
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
      }
      wsRef.current?.close()
    }
  }, [])

  const send = useCallback((data: object) => {
    wsRef.current?.send(JSON.stringify(data))
  }, [])

  const onMessage = useCallback((fn: (msg: M) => void) => {
    listenersRef.current.push(fn)
    return () => {
      listenersRef.current = listenersRef.current.filter(f => f !== fn)
    }
  }, [])

  return { connected, send, onMessage }
}
