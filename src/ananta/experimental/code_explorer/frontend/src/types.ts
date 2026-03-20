export interface RepoInfo {
  project_id: string
  source_url: string
  file_count: number
  analysis_status: string | null
  display_name: string | null
}

export interface RepoAnalysis {
  version: string
  generated_at: string
  head_sha: string
  overview: string
  components: AnalysisComponent[]
  external_dependencies: AnalysisExternalDep[]
  caveats: string
}

export interface AnalysisComponent {
  name: string
  path: string
  description: string
  apis: Array<{ method: string; path: string }>
  models: string[]
  entry_points: string[]
  internal_dependencies: string[]
}

export interface AnalysisExternalDep {
  name: string
  type: string
  description: string
  used_by: string[]
}

export interface UpdateStatus {
  status: string
  files_ingested: number
}

// Re-export shared types that the app needs
export type { TopicInfo, Exchange, ContextBudget, ModelInfo, WSMessage, DocumentItem } from '@shesha/shared-ui'
