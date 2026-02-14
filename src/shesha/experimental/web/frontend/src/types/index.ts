import type {
  TopicInfo,
  TraceStep,
  TraceListItem,
  TraceFull,
  Exchange as SharedExchange,
  ContextBudget,
  ModelInfo,
  WSMessage as SharedWSMessage,
} from '@shesha/shared-ui'

// Re-export shared types that are used as-is in the arxiv frontend.
export type { TopicInfo, TraceStep, TraceListItem, TraceFull, ContextBudget, ModelInfo }

// Arxiv-specific: Exchange uses paper_ids (alias for document_ids).
export interface Exchange extends Omit<SharedExchange, 'document_ids'> {
  paper_ids?: string[]
}

// Arxiv-specific: WSMessage extends shared with paper_ids on complete
// and adds citation-related message types.
export type WSMessage =
  | Exclude<SharedWSMessage, { type: 'complete' }>
  | { type: 'complete'; answer: string; trace_id: string | null; tokens: { prompt: number; completion: number; total: number }; duration_ms: number; paper_ids?: string[] }
  | { type: 'citation_progress'; current: number; total: number; phase?: string }
  | { type: 'citation_report'; papers: PaperReport[] }

// Arxiv-specific types below.

export interface PaperInfo {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  source_type: string | null
}

export interface SearchResult {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  in_topics: string[]
}

export interface MismatchEntry {
  key: string
  message: string
  severity: 'error' | 'warning'
  arxiv_url: string | null
}

export interface LLMPhraseEntry {
  line: number
  text: string
}

export interface TopicalIssueEntry {
  key: string
  message: string
  severity: 'warning'
}

export interface PaperReport {
  arxiv_id: string
  title: string
  arxiv_url: string
  total_citations: number
  verified_count: number
  unresolved_count: number
  mismatch_count: number
  has_issues: boolean
  group: 'verified' | 'unverifiable' | 'issues'
  mismatches: MismatchEntry[]
  llm_phrases: LLMPhraseEntry[]
  topical_issues: TopicalIssueEntry[]
  sources: Record<string, string>
}
