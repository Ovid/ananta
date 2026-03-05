export type { TopicInfo, Exchange, ContextBudget, ModelInfo, WSMessage, DocumentItem } from '@shesha/shared-ui'

export interface DocumentInfo {
  project_id: string
  filename: string
  content_type: string
  size: number
  upload_date: string
  page_count: number | null
}
