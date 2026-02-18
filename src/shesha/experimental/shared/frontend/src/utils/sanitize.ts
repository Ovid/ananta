const BOUNDARY_RE =
  /UNTRUSTED_CONTENT_[0-9a-f]{32}_BEGIN\n?([\s\S]*?)\n?UNTRUSTED_CONTENT_[0-9a-f]{32}_END/g

/**
 * Replace UNTRUSTED_CONTENT boundary markers with markdown blockquotes.
 *
 * The RLM wraps document content in boundary markers for injection defense.
 * When the LLM quotes content verbatim, markers leak into the answer.
 * This converts them to labeled blockquotes for display.
 */
export function stripBoundaryMarkers(text: string): string {
  return text.replace(BOUNDARY_RE, (_match, content: string) => {
    const lines = content.split('\n')
    const quoted = lines.map(line => (line === '' ? '>' : `> ${line}`))
    return `> **Quoted content**\n>\n${quoted.join('\n')}`
  })
}
