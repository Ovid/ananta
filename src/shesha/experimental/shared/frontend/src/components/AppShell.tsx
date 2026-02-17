import type { ReactNode } from 'react'

interface AppShellProps {
  children: ReactNode
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface-0 text-text-primary font-sans">
      {children}
    </div>
  )
}
