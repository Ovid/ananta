import { useState } from 'react'

interface EmailModalProps {
  onSubmit: (email: string) => void
  onSkip: () => void
}

const STORAGE_KEY = 'shesha-polite-email'

export function getStoredEmail(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function storeEmail(email: string): void {
  localStorage.setItem(STORAGE_KEY, email)
}

export function hasEmailDecision(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null || localStorage.getItem('shesha-email-skipped') === 'true'
}

export function markEmailSkipped(): void {
  localStorage.setItem('shesha-email-skipped', 'true')
}

export default function EmailModal({ onSubmit, onSkip }: EmailModalProps) {
  const [email, setEmail] = useState('')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[480px] p-6">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Citation Check — Email</h2>
        <p className="text-xs text-text-secondary leading-relaxed mb-4">
          CrossRef and OpenAlex offer faster access if you provide an email address.
          It's used only as a courtesy identifier in API requests — they never contact you.
          You can skip this, but checks will be slower.
        </p>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && email.trim()) {
              storeEmail(email.trim())
              onSubmit(email.trim())
            }
          }}
          placeholder="your@email.com"
          className="w-full bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent mb-4"
          autoFocus
        />
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => { markEmailSkipped(); onSkip() }}
            className="px-3 py-1.5 text-xs text-text-dim hover:text-text-secondary"
          >
            Skip
          </button>
          <button
            onClick={() => {
              if (email.trim()) {
                storeEmail(email.trim())
                onSubmit(email.trim())
              }
            }}
            disabled={!email.trim()}
            className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent/90 disabled:opacity-50"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  )
}
