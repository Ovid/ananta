import { useState, useCallback, useEffect, useRef, type MouseEvent } from 'react'
import { useTheme } from './useTheme'
import { useWebSocket } from './useWebSocket'
import { sharedApi } from '../api/client'
import type { ContextBudget } from '../types/index'

export interface AppStateOptions {
  onComplete?: () => void
  /**
   * Called for 'error' messages and any unrecognized message types.
   * When provided, error messages are delegated here WITHOUT setting
   * phase='Error' — the consumer must call setPhase('Error') if desired.
   */
  onExtraMessage?: (msg: any) => void
}

export function useAppState(options?: AppStateOptions) {
  const { dark, toggle: toggleTheme } = useTheme()
  const { connected, send, onMessage } = useWebSocket()

  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [modelName, setModelName] = useState('\u2014')
  const [tokens, setTokens] = useState({ prompt: 0, completion: 0, total: 0 })
  const [budget, setBudget] = useState<ContextBudget | null>(null)
  const [phase, setPhase] = useState('Ready')
  const [documentBytes, setDocumentBytes] = useState(0)
  const [sidebarWidth, setSidebarWidth] = useState(224)
  const [historyVersion, setHistoryVersion] = useState(0)
  const [traceView, setTraceView] = useState<{ topic: string; traceId: string } | null>(null)

  const dragging = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options

  // Track activeTopic in a ref for use in the WS handler
  const activeTopicRef = useRef(activeTopic)
  activeTopicRef.current = activeTopic

  // Load model name on mount
  useEffect(() => {
    sharedApi.model.get().then(info => setModelName(info.model)).catch(() => {
      // Model API may not be available yet
    })
  }, [])

  // WebSocket message handler
  useEffect(() => {
    return onMessage((msg: any) => {
      if (msg.type === 'status') {
        setPhase(msg.phase)
      } else if (msg.type === 'step') {
        setPhase(`${msg.step_type} (iter ${msg.iteration})`)
        if (msg.prompt_tokens !== undefined) {
          setTokens({
            prompt: msg.prompt_tokens,
            completion: msg.completion_tokens ?? 0,
            total: msg.prompt_tokens + (msg.completion_tokens ?? 0),
          })
        }
      } else if (msg.type === 'complete') {
        setPhase('Ready')
        setTokens(msg.tokens)
        if (msg.document_bytes != null) setDocumentBytes(msg.document_bytes)
        optionsRef.current?.onComplete?.()
      } else if (msg.type === 'error') {
        if (optionsRef.current?.onExtraMessage) {
          optionsRef.current.onExtraMessage(msg)
        } else {
          setPhase('Error')
        }
      } else if (msg.type === 'cancelled') {
        setPhase('Ready')
      } else {
        optionsRef.current?.onExtraMessage?.(msg)
      }
    })
  }, [onMessage])

  const handleTopicSelect = useCallback((name: string) => {
    setActiveTopic(name)
    if (name) {
      sharedApi.contextBudget(name).then(setBudget).catch(() => {
        // Context budget may not be available for this topic
      })
    }
  }, [])

  const handleViewTrace = useCallback((traceId: string) => {
    const topic = activeTopicRef.current
    if (!topic) return
    setTraceView({ topic, traceId })
  }, [])

  const handleSidebarDrag = useCallback((e: MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX
    const startWidth = sidebarWidth
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!dragging.current) return
      const newWidth = Math.min(600, Math.max(160, startWidth + ev.clientX - startX))
      setSidebarWidth(newWidth)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarWidth])

  return {
    // Theme
    dark, toggleTheme,
    // Connection
    connected, send, onMessage,
    // Status
    modelName, tokens, budget, setBudget, phase, setPhase, documentBytes,
    // Layout
    sidebarWidth, handleSidebarDrag,
    // Navigation
    activeTopic, setActiveTopic, handleTopicSelect,
    traceView, setTraceView, handleViewTrace,
    // History
    historyVersion, setHistoryVersion,
    // Tokens
    setTokens,
  }
}
