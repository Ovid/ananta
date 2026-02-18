import { describe, it, expect } from 'vitest'

import { stripBoundaryMarkers } from '../sanitize'

describe('stripBoundaryMarkers', () => {
  const BOUNDARY = 'UNTRUSTED_CONTENT_bd0e753b7146bd0089d21bfab2c51ded'

  it('replaces boundary markers with labeled blockquote', () => {
    const input = `Before\n${BOUNDARY}_BEGIN\n# Hello\nWorld\n${BOUNDARY}_END\nAfter`
    const result = stripBoundaryMarkers(input)
    expect(result).toContain('> **Quoted content**')
    expect(result).toContain('> # Hello')
    expect(result).toContain('> World')
    expect(result).not.toContain('UNTRUSTED_CONTENT')
    expect(result).toContain('Before')
    expect(result).toContain('After')
  })

  it('handles multiple boundary pairs', () => {
    const hex1 = 'a'.repeat(32)
    const hex2 = 'b'.repeat(32)
    const input = `UNTRUSTED_CONTENT_${hex1}_BEGIN\nFirst\nUNTRUSTED_CONTENT_${hex1}_END\nMiddle\nUNTRUSTED_CONTENT_${hex2}_BEGIN\nSecond\nUNTRUSTED_CONTENT_${hex2}_END`
    const result = stripBoundaryMarkers(input)
    expect(result).not.toContain('UNTRUSTED_CONTENT')
    expect(result).toContain('> First')
    expect(result).toContain('Middle')
    expect(result).toContain('> Second')
  })

  it('preserves blank lines inside quoted content as bare >', () => {
    const input = `${BOUNDARY}_BEGIN\nLine one\n\nLine two\n${BOUNDARY}_END`
    const result = stripBoundaryMarkers(input)
    expect(result).toContain('> Line one')
    expect(result).toContain('>')
    expect(result).toContain('> Line two')
  })

  it('returns text unchanged when no markers present', () => {
    const input = 'Just a normal answer with no markers.'
    expect(stripBoundaryMarkers(input)).toBe(input)
  })

  it('handles markers with different hex values', () => {
    const hex = '0123456789abcdef0123456789abcdef'
    const input = `UNTRUSTED_CONTENT_${hex}_BEGIN\nContent\nUNTRUSTED_CONTENT_${hex}_END`
    const result = stripBoundaryMarkers(input)
    expect(result).not.toContain('UNTRUSTED_CONTENT')
    expect(result).toContain('> Content')
  })

  it('handles marker at very start of text', () => {
    const input = `${BOUNDARY}_BEGIN\nContent\n${BOUNDARY}_END\nAfter`
    const result = stripBoundaryMarkers(input)
    expect(result.startsWith('> **Quoted content**')).toBe(true)
    expect(result).toContain('After')
  })

  it('handles marker at very end of text', () => {
    const input = `Before\n${BOUNDARY}_BEGIN\nContent\n${BOUNDARY}_END`
    const result = stripBoundaryMarkers(input)
    expect(result).toContain('Before')
    expect(result).toContain('> Content')
    expect(result).not.toContain('UNTRUSTED_CONTENT')
  })

  it('leaves orphan BEGIN marker untouched when no END is present', () => {
    const input = `Text ${BOUNDARY}_BEGIN\nContent without end`
    expect(stripBoundaryMarkers(input)).toBe(input)
  })

  it('leaves orphan END marker untouched when no BEGIN is present', () => {
    const input = `Content without begin\n${BOUNDARY}_END rest`
    expect(stripBoundaryMarkers(input)).toBe(input)
  })
})
