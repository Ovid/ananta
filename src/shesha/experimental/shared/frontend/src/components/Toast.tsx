import { useEffect, useState, useCallback } from 'react'

export interface ToastItem {
  id: string
  message: string
  level: 'error' | 'warning' | 'success' | 'info'
}

const levelColors: Record<string, string> = {
  error: 'border-red bg-red/10 text-red',
  warning: 'border-amber bg-amber/10 text-amber',
  success: 'border-green bg-green/10 text-green',
  info: 'border-accent bg-accent-dim text-accent',
}

let addToastExternal: ((item: Omit<ToastItem, 'id'>) => void) | null = null

/** Call from anywhere to show a toast notification. */
export function showToast(message: string, level: ToastItem['level'] = 'info') {
  addToastExternal?.({ message, level })
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((item: Omit<ToastItem, 'id'>) => {
    const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts(prev => [...prev, { ...item, id }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 8000)
  }, [])

  useEffect(() => {
    addToastExternal = addToast
    return () => { addToastExternal = null }
  }, [addToast])

  const dismiss = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-10 right-4 flex flex-col gap-2 z-50 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`border rounded px-3 py-2 text-sm flex items-start gap-2 shadow-lg ${levelColors[toast.level]}`}
        >
          <span className="flex-1">{toast.message}</span>
          <button
            onClick={() => dismiss(toast.id)}
            className="opacity-60 hover:opacity-100 text-xs leading-none mt-0.5"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  )
}
