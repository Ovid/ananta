import type { ReactNode } from 'react'

interface AppShellProps {
  children: ReactNode
  connected?: boolean
}

export default function AppShell({ children, connected }: AppShellProps) {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface-0 text-text-primary font-sans">
      {connected === false && (
        <div className="bg-amber/10 border-b border-amber text-amber text-sm px-4 py-1.5 text-center">
          Connection lost. Reconnecting...
        </div>
      )}
      {children}
    </div>
  )
}
