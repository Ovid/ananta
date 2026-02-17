import { Header as SharedHeader } from '@shesha/shared-ui'

interface ArxivHeaderProps {
  onSearchToggle: () => void
  onCheckCitations: () => void
  onExport: () => void
  onHelpToggle: () => void
  dark: boolean
  onThemeToggle: () => void
}

export default function Header({
  onSearchToggle,
  onCheckCitations,
  onExport,
  onHelpToggle,
  dark,
  onThemeToggle,
}: ArxivHeaderProps) {
  return (
    <SharedHeader appName="arXiv Explorer" isDark={dark} onToggleTheme={onThemeToggle}>
      <button
        onClick={onSearchToggle}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Search arXiv"
        data-tooltip="Search arXiv"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </button>
      <button
        onClick={onCheckCitations}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Check citations"
        data-tooltip="Check citations"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>
      <button
        onClick={onExport}
        className="tooltip-btn p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
        aria-label="Export transcript"
        data-tooltip="Export transcript"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </button>
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
    </SharedHeader>
  )
}
