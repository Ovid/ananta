import type { RepoInfo, RepoAnalysis } from '../types'

interface RepoDetailProps {
  repo: RepoInfo
  analysis: RepoAnalysis | null
  onClose: () => void
  onAnalyze: (projectId: string) => void
  onCheckUpdates: (projectId: string) => void
  onRemove: (projectId: string) => void
}

function statusBadgeClass(status: string | null): string {
  switch (status) {
    case 'current':
      return 'text-green bg-green/10 border-green/30'
    case 'stale':
      return 'text-amber bg-amber/10 border-amber/30'
    default:
      return 'text-red bg-red/10 border-red/30'
  }
}

function statusLabel(status: string | null): string {
  return status ?? 'missing'
}

export default function RepoDetail({
  repo,
  analysis,
  onClose,
  onAnalyze,
  onCheckUpdates,
  onRemove,
}: RepoDetailProps) {
  const status = repo.analysis_status
  const showGenerate = !status || status === 'missing'
  const showRegenerate = status === 'stale'

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-surface-1">
        <h1 className="text-lg font-semibold text-text-primary flex-1 min-w-0 truncate">
          {repo.project_id}
        </h1>
        <a
          href={repo.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-accent hover:underline truncate"
        >
          {repo.source_url}
        </a>
        <button
          onClick={onClose}
          aria-label="close"
          className="text-text-secondary hover:text-text-primary transition-colors text-lg leading-none px-1"
        >
          &times;
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
        {/* Stats row */}
        <div className="flex items-center gap-4 text-sm">
          <span className="text-text-secondary">{repo.file_count} files</span>
          <span
            className={`px-2 py-0.5 text-xs font-medium rounded border ${statusBadgeClass(status)}`}
          >
            {statusLabel(status)}
          </span>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3 mt-4">
          {showGenerate && (
            <button
              onClick={() => onAnalyze(repo.project_id)}
              className="px-3 py-1.5 text-xs bg-accent text-surface-0 rounded font-medium hover:bg-accent/90 transition-colors"
            >
              Generate Analysis
            </button>
          )}
          {showRegenerate && (
            <button
              onClick={() => onAnalyze(repo.project_id)}
              className="px-3 py-1.5 text-xs bg-accent text-surface-0 rounded font-medium hover:bg-accent/90 transition-colors"
            >
              Regenerate Analysis
            </button>
          )}
          <button
            onClick={() => onCheckUpdates(repo.project_id)}
            className="px-3 py-1.5 text-xs text-text-secondary border border-border rounded hover:text-text-primary hover:border-text-dim transition-colors"
          >
            Check for Updates
          </button>
          <div className="flex-1" />
          <button
            onClick={() => onRemove(repo.project_id)}
            className="px-3 py-1.5 text-xs text-red border border-red/30 rounded hover:bg-red/10 transition-colors"
          >
            Remove
          </button>
        </div>

        {/* Analysis content or empty state */}
        {analysis ? (
          <div className="mt-6 space-y-6">
            {/* Overview */}
            <section>
              <h2 className="text-sm font-semibold text-text-primary mb-2">Overview</h2>
              <p className="text-sm text-text-secondary leading-relaxed">{analysis.overview}</p>
            </section>

            {/* Components */}
            {analysis.components.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-text-primary mb-2">Components</h2>
                <div className="space-y-3">
                  {analysis.components.map((comp) => (
                    <div
                      key={comp.name}
                      className="border border-border rounded p-3 bg-surface-1"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-text-primary">{comp.name}</span>
                        <span className="text-xs text-text-dim font-mono">{comp.path}</span>
                      </div>
                      <p className="text-xs text-text-secondary mt-1">{comp.description}</p>
                      {comp.apis.length > 0 && (
                        <div className="mt-2">
                          <span className="text-xs text-text-dim">APIs: </span>
                          {comp.apis.map((api, i) => (
                            <span key={i} className="text-xs text-text-secondary font-mono">
                              {api.method} {api.path}
                              {i < comp.apis.length - 1 ? ', ' : ''}
                            </span>
                          ))}
                        </div>
                      )}
                      {comp.models.length > 0 && (
                        <div className="mt-1">
                          <span className="text-xs text-text-dim">Models: </span>
                          <span className="text-xs text-text-secondary">
                            {comp.models.join(', ')}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* External Dependencies */}
            {analysis.external_dependencies.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-text-primary mb-2">
                  External Dependencies
                </h2>
                <div className="space-y-2">
                  {analysis.external_dependencies.map((dep) => (
                    <div key={dep.name} className="flex items-start gap-3 text-sm">
                      <span className="font-medium text-text-primary">{dep.name}</span>
                      <span className="text-xs text-text-dim px-1.5 py-0.5 border border-border rounded">
                        {dep.type}
                      </span>
                      <span className="text-text-secondary">{dep.description}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Caveats */}
            {analysis.caveats && (
              <section>
                <h2 className="text-sm font-semibold text-text-primary mb-2">Caveats</h2>
                <p className="text-xs text-text-dim leading-relaxed">{analysis.caveats}</p>
              </section>
            )}
          </div>
        ) : (
          <p className="mt-6 text-sm text-text-dim">
            No analysis available. Click &apos;Generate Analysis&apos; to create one.
          </p>
        )}
      </div>
    </div>
  )
}
