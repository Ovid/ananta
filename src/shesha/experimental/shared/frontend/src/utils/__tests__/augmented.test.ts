import { describe, it, expect } from 'vitest'
import { splitAugmentedSections } from '../augmented'

describe('splitAugmentedSections', () => {
  it('returns single document segment when no markers present', () => {
    const result = splitAugmentedSections('Just a normal answer.')
    expect(result).toEqual([{ type: 'document', content: 'Just a normal answer.' }])
  })

  it('splits content at background knowledge markers', () => {
    const input = 'Document content.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nInferred content.\n<!-- BACKGROUND_KNOWLEDGE_END -->\nMore document content.'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(3)
    expect(result[0]).toEqual({ type: 'document', content: 'Document content.' })
    expect(result[1]).toEqual({ type: 'background', content: 'Inferred content.' })
    expect(result[2]).toEqual({ type: 'document', content: 'More document content.' })
  })

  it('handles multiple background sections', () => {
    const input = 'A\n<!-- BACKGROUND_KNOWLEDGE_START -->\nB\n<!-- BACKGROUND_KNOWLEDGE_END -->\nC\n<!-- BACKGROUND_KNOWLEDGE_START -->\nD\n<!-- BACKGROUND_KNOWLEDGE_END -->\nE'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(5)
    expect(result[0]).toEqual({ type: 'document', content: 'A' })
    expect(result[1]).toEqual({ type: 'background', content: 'B' })
    expect(result[2]).toEqual({ type: 'document', content: 'C' })
    expect(result[3]).toEqual({ type: 'background', content: 'D' })
    expect(result[4]).toEqual({ type: 'document', content: 'E' })
  })

  it('handles background section at start of text', () => {
    const input = '<!-- BACKGROUND_KNOWLEDGE_START -->\nInferred.\n<!-- BACKGROUND_KNOWLEDGE_END -->\nDocument.'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ type: 'background', content: 'Inferred.' })
    expect(result[1]).toEqual({ type: 'document', content: 'Document.' })
  })

  it('handles background section at end of text', () => {
    const input = 'Document.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nInferred.\n<!-- BACKGROUND_KNOWLEDGE_END -->'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ type: 'document', content: 'Document.' })
    expect(result[1]).toEqual({ type: 'background', content: 'Inferred.' })
  })

  it('filters out empty segments', () => {
    const input = '<!-- BACKGROUND_KNOWLEDGE_START -->\nContent\n<!-- BACKGROUND_KNOWLEDGE_END -->'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({ type: 'background', content: 'Content' })
  })

  it('preserves multiline content within background section', () => {
    const input = 'Doc.\n<!-- BACKGROUND_KNOWLEDGE_START -->\nLine 1\n\nLine 2\n\n- bullet\n<!-- BACKGROUND_KNOWLEDGE_END -->'
    const result = splitAugmentedSections(input)
    expect(result[1].content).toBe('Line 1\n\nLine 2\n\n- bullet')
  })

  it('treats malformed markers (no END) as document content', () => {
    const input = 'Before\n<!-- BACKGROUND_KNOWLEDGE_START -->\nOrphan content'
    const result = splitAugmentedSections(input)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ type: 'document', content: 'Before' })
    expect(result[1]).toEqual({ type: 'document', content: 'Orphan content' })
  })
})
