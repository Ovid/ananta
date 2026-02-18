# Boundary Marker Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace raw `UNTRUSTED_CONTENT_{hex}_BEGIN/END` markers in RLM answers with styled markdown blockquotes labeled "Quoted content".

**Architecture:** A pure-function utility in shared-ui transforms answer text before react-markdown renders it. The function finds boundary marker pairs via regex and converts enclosed content to markdown blockquote syntax. The shared ChatMessage calls it by default; the web app's custom renderer calls it before citation parsing.

**Tech Stack:** TypeScript, vitest, react-markdown (existing), @shesha/shared-ui

---

### Task 1: Create stripBoundaryMarkers utility with tests

**Files:**
- Create: `src/shesha/experimental/shared/frontend/src/utils/sanitize.ts`
- Create: `src/shesha/experimental/shared/frontend/src/utils/__tests__/sanitize.test.ts`

**Step 1: Write the failing tests**

Create the test file:

```typescript
// src/shesha/experimental/shared/frontend/src/utils/__tests__/sanitize.test.ts
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
    expect(result).toStartWith('> **Quoted content**')
    expect(result).toContain('After')
  })

  it('handles marker at very end of text', () => {
    const input = `Before\n${BOUNDARY}_BEGIN\nContent\n${BOUNDARY}_END`
    const result = stripBoundaryMarkers(input)
    expect(result).toContain('Before')
    expect(result).toContain('> Content')
    expect(result).not.toContain('UNTRUSTED_CONTENT')
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/utils/__tests__/sanitize.test.ts`
Expected: FAIL — module `../sanitize` not found

**Step 3: Write minimal implementation**

```typescript
// src/shesha/experimental/shared/frontend/src/utils/sanitize.ts

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
```

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/utils/__tests__/sanitize.test.ts`
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/utils/sanitize.ts src/shesha/experimental/shared/frontend/src/utils/__tests__/sanitize.test.ts
git commit -m "feat: add stripBoundaryMarkers utility for answer text"
```

---

### Task 2: Integrate into shared ChatMessage

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx:1-4,42-44`
- Modify: `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatMessage.test.tsx`

**Step 1: Write the failing test**

Add to the existing test file `ChatMessage.test.tsx`:

```typescript
  it('strips boundary markers from answer before rendering', () => {
    const hex = 'bd0e753b7146bd0089d21bfab2c51ded'
    const exchange = {
      ...baseExchange,
      answer: `Here is the content:\nUNTRUSTED_CONTENT_${hex}_BEGIN\n# Hello World\nUNTRUSTED_CONTENT_${hex}_END`,
    }
    render(
      <ChatMessage exchange={exchange} onViewTrace={vi.fn()} />
    )
    expect(screen.queryByText(/UNTRUSTED_CONTENT/)).not.toBeInTheDocument()
    expect(screen.getByText('Quoted content')).toBeInTheDocument()
  })
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: FAIL — "UNTRUSTED_CONTENT" is found in the rendered output

**Step 3: Modify ChatMessage to use stripBoundaryMarkers**

In `ChatMessage.tsx`, add the import and use it in the default markdown path:

```typescript
// Add import at top:
import { stripBoundaryMarkers } from '../utils/sanitize'

// Change line 44 from:
//   : <Markdown components={mdComponents}>{exchange.answer}</Markdown>}
// to:
//   : <Markdown components={mdComponents}>{stripBoundaryMarkers(exchange.answer)}</Markdown>}
```

**Step 4: Run tests to verify they pass**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: PASS (all 11 tests, including the new one)

**Step 5: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/components/ChatMessage.tsx src/shesha/experimental/shared/frontend/src/components/__tests__/ChatMessage.test.tsx
git commit -m "feat: strip boundary markers in shared ChatMessage"
```

---

### Task 3: Export from shared-ui barrel and integrate into web app

**Files:**
- Modify: `src/shesha/experimental/shared/frontend/src/index.ts`
- Modify: `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx:72-73`

**Step 1: Export stripBoundaryMarkers from shared-ui index.ts**

Add to `index.ts`:

```typescript
// Utils
export { stripBoundaryMarkers } from './utils/sanitize'
```

**Step 2: Integrate into web app's ChatMessage**

In `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx`, the custom `renderAnswer` passes the raw answer to `renderAnswerWithCitations`. Add `stripBoundaryMarkers` before citation parsing:

```typescript
// Add import:
import { stripBoundaryMarkers } from '@shesha/shared-ui'

// Change line 72-73 from:
//   const renderAnswer = (answer: string): ReactNode => (
//     <>{renderAnswerWithCitations(answer, topicPapers, onPaperClick)}</>
//   )
// to:
//   const renderAnswer = (answer: string): ReactNode => (
//     <>{renderAnswerWithCitations(stripBoundaryMarkers(answer), topicPapers, onPaperClick)}</>
//   )
```

**Step 3: Run all frontend tests**

Run: `cd src/shesha/experimental/shared/frontend && npx vitest run`
Expected: PASS (all shared-ui tests)

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: PASS (all web app tests)

**Step 4: Commit**

```bash
git add src/shesha/experimental/shared/frontend/src/index.ts src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx
git commit -m "feat: export stripBoundaryMarkers and integrate into web app"
```

---

### Task 4: Also integrate into web app ChatArea (streaming path)

The web app has a **second** `renderAnswerWithCitations` in `ChatArea.tsx` that handles the streaming/live message path.

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/ChatArea.tsx:100-102`

**Step 1: Check the web app ChatArea**

Read `src/shesha/experimental/web/frontend/src/components/ChatArea.tsx` and find the `renderAnswer` callback around line 100.

**Step 2: Add stripBoundaryMarkers there too**

```typescript
// Add import:
import { stripBoundaryMarkers } from '@shesha/shared-ui'

// Change the renderAnswer callback from:
//   const renderAnswer = useCallback(
//     (answer: string) => <>{renderAnswerWithCitations(answer, topicPapers, onPaperClick)}</>,
//     [topicPapers, onPaperClick]
//   )
// to:
//   const renderAnswer = useCallback(
//     (answer: string) => <>{renderAnswerWithCitations(stripBoundaryMarkers(answer), topicPapers, onPaperClick)}</>,
//     [topicPapers, onPaperClick]
//   )
```

**Step 3: Run web app tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: PASS

**Step 4: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/ChatArea.tsx
git commit -m "feat: strip boundary markers in web app ChatArea streaming path"
```

---

### Task 5: Run full test suite and verify

**Step 1: Run make all**

Run: `make all`
Expected: All Python tests pass (1643+), all JS tests pass, mypy clean, ruff clean

**Step 2: Run web app frontend tests separately**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: PASS (66+ tests)

**Step 3: Verify no regressions**

Check that existing ChatMessage tests still pass — the boundary stripping should be transparent when no markers are present.
