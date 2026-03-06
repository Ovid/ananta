interface HelpPanelProps {
  onClose: () => void
  quickStart: string[]
  faq: { q: string; a: string }[]
  shortcuts: { label: string; key: string }[]
}

export default function HelpPanel({ onClose, quickStart, faq, shortcuts }: HelpPanelProps) {
  return (
    <div className="fixed inset-y-0 right-0 w-[400px] bg-surface-1 border-l border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">Help</h2>
        <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg">&times;</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6 text-sm">
        {/* Quick Start */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Quick Start</h3>
          <ol className="list-decimal list-inside space-y-1 text-text-secondary">
            {quickStart.map((step, i) => (
              <li key={i} dangerouslySetInnerHTML={{ __html: step }} />
            ))}
          </ol>
        </section>

        {/* FAQ */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">FAQ</h3>
          <div className="space-y-3">
            {faq.map((item, i) => (
              <div key={i}>
                <p className="text-text-primary font-medium" dangerouslySetInnerHTML={{ __html: item.q }} />
                <p className="text-text-dim" dangerouslySetInnerHTML={{ __html: item.a }} />
              </div>
            ))}
          </div>
        </section>

        {/* Keyboard Shortcuts */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Keyboard Shortcuts</h3>
          <div className="space-y-1 text-text-secondary">
            {shortcuts.map((s, i) => (
              <div key={i} className="flex justify-between">
                <span>{s.label}</span>
                <kbd className="bg-surface-2 border border-border px-1.5 rounded text-xs font-mono">{s.key}</kbd>
              </div>
            ))}
          </div>
        </section>

        {/* Experimental notice */}
        <section className="bg-amber/5 border border-amber/20 rounded p-3 text-xs text-amber">
          This is experimental software. Features may change or break. Please <a href="https://github.com/Ovid/shesha/issues" target="_blank" rel="noopener noreferrer" className="underline hover:text-amber/80">report issues</a>.
        </section>
      </div>
    </div>
  )
}
