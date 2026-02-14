// Barrel exports will be added as components are extracted in Tasks 13-19.
// Each extraction task adds its export line here.
export type { TopicInfo, DocumentItem, TraceStep, TraceListItem, TraceFull, Exchange, ContextBudget, ModelInfo, WSMessage } from './types'
export { useWebSocket } from './hooks/useWebSocket'
export { useTheme } from './hooks/useTheme'

// Components
export { default as ConfirmDialog } from './components/ConfirmDialog'
export { default as StatusBar } from './components/StatusBar'
export { default as ToastContainer, showToast } from './components/Toast'
export type { ToastItem } from './components/Toast'
export { default as TraceViewer } from './components/TraceViewer'
export { default as Header } from './components/Header'
export { default as ChatArea } from './components/ChatArea'
export type { ChatAreaProps } from './components/ChatArea'
export { default as ChatMessage } from './components/ChatMessage'
export type { ChatMessageProps } from './components/ChatMessage'
export { default as TopicSidebar } from './components/TopicSidebar'
export type { TopicSidebarProps } from './components/TopicSidebar'
