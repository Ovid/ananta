export interface AugmentedSection {
  type: 'document' | 'background'
  content: string
}

const BG_START = '<!-- BACKGROUND_KNOWLEDGE_START -->'
const BG_END = '<!-- BACKGROUND_KNOWLEDGE_END -->'

export function splitAugmentedSections(text: string): AugmentedSection[] {
  const sections: AugmentedSection[] = []
  let remaining = text

  while (remaining.length > 0) {
    const startIdx = remaining.indexOf(BG_START)
    if (startIdx === -1) {
      const trimmed = remaining.trim()
      if (trimmed) sections.push({ type: 'document', content: trimmed })
      break
    }

    const before = remaining.slice(0, startIdx).trim()
    if (before) sections.push({ type: 'document', content: before })

    const afterStart = remaining.slice(startIdx + BG_START.length)
    const endIdx = afterStart.indexOf(BG_END)
    if (endIdx === -1) {
      const rest = afterStart.trim()
      if (rest) sections.push({ type: 'document', content: rest })
      break
    }

    const bgContent = afterStart.slice(0, endIdx).trim()
    if (bgContent) sections.push({ type: 'background', content: bgContent })

    remaining = afterStart.slice(endIdx + BG_END.length)
  }

  return sections
}
