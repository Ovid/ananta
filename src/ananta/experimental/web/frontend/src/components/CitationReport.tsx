import type { PaperReport } from '../types'

interface CitationReportProps {
  checking: boolean
  progress: { current: number; total: number; phase?: string } | null
  report: PaperReport[] | null
  error: string | null
  onClose: () => void
}

const DISCLAIMER =
  'DISCLAIMER: This analysis is generated using AI and automated heuristics. ' +
  'It is capable of making mistakes. A flagged citation does NOT mean a paper is ' +
  'fraudulent \u2014 there may be legitimate explanations (metadata lag, preprint ' +
  'title changes, version differences). Always verify findings manually before ' +
  'drawing conclusions.'

const SOURCE_LABELS: Record<string, string> = {
  arxiv: 'arXiv',
  crossref: 'CrossRef',
  openalex: 'OpenAlex',
  semantic_scholar: 'S2',
}

function SourceBadge({ source }: { source: string }) {
  const label = SOURCE_LABELS[source] ?? source
  return (
    <span className="text-[10px] px-1 py-0.5 rounded bg-surface-2 text-text-dim border border-border">
      {label}
    </span>
  )
}

export default function CitationReport({ checking, progress, report, error, onClose }: CitationReportProps) {
  if (!checking && !report && !error) return null

  const verified = report?.filter(p => p.group === 'verified') ?? []
  const unverifiable = report?.filter(p => p.group === 'unverifiable') ?? []
  const issues = report?.filter(p => p.group === 'issues') ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[700px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Citation Check</h2>
          <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg leading-none">&times;</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {/* Loading states */}
          {checking && progress && (
            <div className="text-center py-8">
              <div className="text-sm text-text-secondary mb-2">
                {progress.current}/{progress.total} &mdash; {progress.phase ?? 'Checking...'}
              </div>
              <div className="w-full bg-surface-2 rounded-full h-2">
                <div
                  className="bg-accent h-2 rounded-full transition-all"
                  style={{ width: `${(progress.current / progress.total) * 100}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="text-center py-8 text-red text-sm">{error}</div>
          )}

          {checking && !progress && !error && (
            <div className="text-center py-8 text-text-dim text-sm">
              Starting citation check...
            </div>
          )}

          {/* Report content */}
          {report && (
            <>
              {/* Zone 1: Disclaimer */}
              <div className="rounded border border-red/30 bg-red/5 px-3 py-2">
                <p className="text-xs font-bold text-red leading-relaxed">{DISCLAIMER}</p>
              </div>

              {/* Zone 2: Verified papers */}
              {verified.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-green mb-1">
                    All citations verified ({verified.length})
                  </h3>
                  <ul className="space-y-0.5">
                    {verified.map(p => {
                      const uniqueSources = [...new Set(Object.values(p.sources ?? {}))]
                      return (
                        <li key={p.arxiv_id} className="flex items-baseline gap-1.5 text-xs text-text-secondary">
                          <span className="text-green shrink-0">&#10003;</span>
                          <span className="truncate">{p.title}</span>
                          <span className="text-text-dim shrink-0">
                            ({p.verified_count}/{p.total_citations} verified)
                          </span>
                          {uniqueSources.map(s => <SourceBadge key={s} source={s} />)}
                          <a
                            href={p.arxiv_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent hover:underline shrink-0"
                          >
                            arXiv
                          </a>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              )}

              {/* Zone 3: Unverifiable papers */}
              {unverifiable.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-text-dim mb-1">
                    Some citations could not be checked ({unverifiable.length})
                  </h3>
                  <ul className="space-y-0.5">
                    {unverifiable.map(p => (
                      <li key={p.arxiv_id} className="flex items-baseline gap-1.5 text-xs text-text-secondary">
                        <span className="text-text-dim shrink-0">&#8212;</span>
                        <span className="truncate">{p.title}</span>
                        <span className="text-text-dim shrink-0">
                          ({p.verified_count} verified, {p.unresolved_count} not found in databases)
                        </span>
                        <a
                          href={p.arxiv_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent hover:underline shrink-0"
                        >
                          arXiv
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Zone 4: Papers with issues */}
              {issues.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold text-amber mb-1">
                    Potential issues detected ({issues.length})
                  </h3>
                  {issues.map(p => (
                    <div key={p.arxiv_id} className="rounded border border-border bg-surface-2 px-3 py-2">
                      {/* Paper header */}
                      <div className="flex items-baseline gap-1.5 mb-1.5">
                        <span className="text-amber shrink-0">&#9888;</span>
                        <span className="text-xs font-medium text-text-primary truncate">{p.title}</span>
                        <a
                          href={p.arxiv_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent hover:underline shrink-0"
                        >
                          arXiv
                        </a>
                      </div>

                      {/* Citation stats */}
                      <div className="text-xs text-text-dim mb-1.5">
                        {p.total_citations === 0 ? (
                          <span className="text-amber">No citations could be extracted</span>
                        ) : (
                          <>
                            {p.total_citations} citations
                            {p.verified_count > 0 && <> &middot; {p.verified_count} OK</>}
                            {p.unresolved_count > 0 && <> &middot; {p.unresolved_count} not found in databases</>}
                            {p.mismatch_count > 0 && <> &middot; <span className="text-red">{p.mismatch_count} mismatches</span></>}
                          </>
                        )}
                      </div>

                      {/* Mismatch details */}
                      {p.mismatches.length > 0 && (
                        <div className="space-y-1 mb-1.5">
                          {p.mismatches.map((m, i) => (
                            <div
                              key={i}
                              className={`text-xs pl-4 border-l-2 ${
                                m.severity === 'error'
                                  ? 'border-red text-red'
                                  : 'border-amber text-amber'
                              }`}
                            >
                              <div>
                                <span className="font-mono">[{m.key}]</span>: {m.message}
                              </div>
                              {m.arxiv_url && (
                                <a
                                  href={m.arxiv_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-accent hover:underline"
                                >
                                  {m.arxiv_url}
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Topical issues */}
                      {(p.topical_issues ?? []).length > 0 && (
                        <div className="space-y-1 mb-1.5">
                          <div className="text-xs text-orange-400 font-medium">Topically unrelated:</div>
                          {p.topical_issues.map((ti, i) => (
                            <div key={i} className="text-xs pl-4 border-l-2 border-orange-400 text-orange-400">
                              <span className="font-mono">[{ti.key}]</span>: {ti.message}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* LLM-tell phrases */}
                      {p.llm_phrases.length > 0 && (
                        <div className="text-xs">
                          <div className="text-purple-400 font-medium mb-0.5">LLM-tell phrases:</div>
                          {p.llm_phrases.map((lp, i) => (
                            <div key={i} className="text-purple-400/70 pl-4">
                              Line {lp.line}: &ldquo;{lp.text}&rdquo;
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
