import type { ReactNode } from 'react'
import type { Components } from 'react-markdown'

import { mdComponents } from '@shesha/shared-ui'
import type { PaperInfo } from '../types'

const CITATION_RE = /\[@arxiv:([^\]]+)\]/g
const ARXIV_ID_RE = /(?:[\w.-]+\/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?/g

/**
 * Convert [@arxiv:ID] citation patterns into Markdown links: [ID](arxiv:ID).
 * Semicolon-separated IDs within a single tag become individual links.
 * Unknown patterns (no valid arxiv IDs) are preserved as literal text.
 */
export function preprocessCitations(text: string): string {
  return text.replace(CITATION_RE, (_match, rawContent: string) => {
    const ids = [...rawContent.matchAll(ARXIV_ID_RE)].map(m => m[0])
    if (ids.length === 0) return _match
    return ids.map(id => `[${id}](arxiv:${id})`).join(' ')
  })
}

/**
 * Build react-markdown Components that extend mdComponents with a custom `a`
 * renderer: arxiv: protocol links become clickable citation buttons when the
 * paper is found in topicPapers; otherwise they render as plain text.
 * Non-arxiv links render as normal <a> tags.
 */
export function buildCitationComponents(
  topicPapers?: PaperInfo[],
  onPaperClick?: (paper: PaperInfo) => void,
): Components {
  return {
    ...mdComponents,
    a: ({ href, children }): ReactNode => {
      if (href?.startsWith('arxiv:')) {
        const arxivId = href.slice('arxiv:'.length)
        const paper = topicPapers?.find(p => p.arxiv_id === arxivId)
        if (paper) {
          return (
            <button
              type="button"
              onClick={() => onPaperClick?.(paper)}
              className="text-xs text-accent hover:underline bg-accent/5 rounded px-1 py-0.5 mx-0.5 inline"
              title={paper.title}
            >
              {children}
            </button>
          )
        }
        // Unknown paper — render as plain text
        return <>{children}</>
      }
      // Non-arxiv link — render as normal anchor
      return <a href={href}>{children}</a>
    },
  }
}
