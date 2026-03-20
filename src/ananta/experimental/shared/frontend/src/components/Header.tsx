import { useState } from 'react'
import type { ReactNode } from 'react'

interface HeaderProps {
  appName: string
  isDark: boolean
  onToggleTheme: () => void
  onHelpToggle?: () => void
  children?: ReactNode
}

export default function Header({
  appName,
  isDark,
  onToggleTheme,
  onHelpToggle,
  children,
}: HeaderProps) {
  const [logoError, setLogoError] = useState(false)

  return (
    <header className="h-13 border-b border-border bg-surface-1 flex items-center px-4 shrink-0">
      {/* Logo + Title */}
      <div className="flex items-baseline gap-2">
        {logoError ? (
          <div className="w-8 h-8 rounded bg-accent flex items-center justify-center text-surface-0 font-bold text-sm self-center">
            S
          </div>
        ) : (
          <img
            src="/static/shesha.png"
            alt="Shesha"
            className="w-8 h-8 self-center rounded-md"
            onError={() => setLogoError(true)}
          />
        )}
        <a href="https://github.com/Ovid/shesha" target="_blank" rel="noopener noreferrer" className="text-base font-bold text-text-primary hover:text-accent transition-colors">Shesha</a>
        <span className="text-xs text-text-dim font-mono">{appName}</span>
        <span className="text-[10px] text-amber border border-amber/40 rounded-full px-2 py-0.5 font-medium">
          Experimental
        </span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action buttons */}
      <div className="flex items-center gap-1">
        {children}

        {/* Help button — shown when onHelpToggle is provided */}
        {onHelpToggle && (
          <button
            onClick={onHelpToggle}
            className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
            aria-label="Help"
            data-tooltip="Help"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
        )}

        {/* Bug report link */}
        <a
          href="https://github.com/Ovid/shesha/issues"
          target="_blank"
          rel="noopener noreferrer"
          className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          aria-label="Report a bug"
          data-tooltip="Report a bug"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 12.75c1.148 0 2.278.08 3.383.237 1.037.146 1.866.966 1.866 2.013 0 3.728-2.35 6.75-5.25 6.75S6.75 18.728 6.75 15c0-1.046.83-1.867 1.866-2.013A24.204 24.204 0 0112 12.75zm0 0c2.883 0 5.647.508 8.207 1.44m-16.414 0A23.924 23.924 0 0112 12.75" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 6.438c.547-.37.978-.87 1.244-1.456M8.25 6.438A3.746 3.746 0 017.006 4.98M15.75 6.438V8.25m-7.5-1.812V8.25m0 0h7.5M8.25 8.25v1.5c0 .26.013.517.039.77m7.461-.77a12.037 12.037 0 01.039-.77" />
          </svg>
        </a>

        {/* Divider */}
        <div className="w-px h-6 bg-border mx-1" />

        {/* Theme toggle */}
        <button
          onClick={onToggleTheme}
          className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          aria-label={isDark ? 'Light mode' : 'Dark mode'}
          data-tooltip={isDark ? 'Light mode' : 'Dark mode'}
        >
          {isDark ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
