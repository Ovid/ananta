import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import PaperDetail from '../PaperDetail'
import type { PaperInfo } from '../../types'

const PAPER: PaperInfo = {
  arxiv_id: '2401.12345v1',
  title: 'Attention Is All You Need',
  authors: ['A. Vaswani', 'N. Shazeer'],
  abstract: 'We propose a new architecture.',
  category: 'cs.CL',
  date: '2024-01-15',
  arxiv_url: 'https://arxiv.org/abs/2401.12345v1',
  source_type: null,
}

describe('PaperDetail HTML sanitization', () => {
  it('escapes HTML in abstract before rendering LaTeX', () => {
    const maliciousPaper: PaperInfo = {
      ...PAPER,
      abstract: 'Safe text <script>alert("xss")</script> more text',
    }
    const { container } = render(
      <PaperDetail paper={maliciousPaper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    // The script tag must not appear as an actual DOM element
    expect(container.querySelector('script')).toBeNull()
    // The escaped text should be visible
    expect(container.textContent).toContain('<script>')
  })

  it('escapes HTML in title before rendering LaTeX', () => {
    const maliciousPaper: PaperInfo = {
      ...PAPER,
      title: 'Title <img src=x onerror=alert(1)>',
    }
    const { container } = render(
      <PaperDetail paper={maliciousPaper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    expect(container.querySelector('img')).toBeNull()
  })

  it('renders \\emph as italic', () => {
    const paper: PaperInfo = {
      ...PAPER,
      abstract: 'Chess is the \\emph{Drosophila} of AI.',
    }
    const { container } = render(
      <PaperDetail paper={paper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    const em = container.querySelector('em')
    expect(em).not.toBeNull()
    expect(em!.textContent).toBe('Drosophila')
    // The raw \emph command should not appear
    expect(container.textContent).not.toContain('\\emph')
  })

  it('renders \\textbf as bold', () => {
    const paper: PaperInfo = {
      ...PAPER,
      abstract: 'This is \\textbf{important} stuff.',
    }
    const { container } = render(
      <PaperDetail paper={paper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    const strong = container.querySelector('strong')
    expect(strong).not.toBeNull()
    expect(strong!.textContent).toBe('important')
  })

  it('renders \\textit as italic', () => {
    const paper: PaperInfo = {
      ...PAPER,
      abstract: 'See \\textit{figure 1} for details.',
    }
    const { container } = render(
      <PaperDetail paper={paper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    const em = container.querySelector('em')
    expect(em).not.toBeNull()
    expect(em!.textContent).toBe('figure 1')
  })

  it('renders \\texttt as code', () => {
    const paper: PaperInfo = {
      ...PAPER,
      abstract: 'Use the \\texttt{FictPlay} algorithm.',
    }
    const { container } = render(
      <PaperDetail paper={paper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    const code = container.querySelector('code')
    expect(code).not.toBeNull()
    expect(code!.textContent).toBe('FictPlay')
  })

  it('still renders LaTeX math after escaping HTML', () => {
    const paper: PaperInfo = {
      ...PAPER,
      abstract: 'The loss is $L = \\sum x_i$ end.',
    }
    const { container } = render(
      <PaperDetail paper={paper} topicName="nlp" onRemove={() => {}} onClose={() => {}} />
    )
    // KaTeX should produce .katex elements
    expect(container.querySelector('.katex')).not.toBeNull()
  })
})

describe('PaperDetail remove confirmation', () => {
  it('shows styled confirm dialog instead of native confirm', async () => {
    render(
      <PaperDetail
        paper={PAPER}
        topicName="nlp"
        onRemove={() => {}}
        onClose={() => {}}
      />
    )
    await userEvent.click(screen.getByText('Remove from topic'))
    // Should show a styled dialog, not a native confirm
    expect(screen.getByText('Remove paper')).toBeInTheDocument()
  })

  it('shows paper title in confirmation message, not arxiv_id', async () => {
    render(
      <PaperDetail
        paper={PAPER}
        topicName="nlp"
        onRemove={() => {}}
        onClose={() => {}}
      />
    )
    await userEvent.click(screen.getByText('Remove from topic'))
    // The dialog message should reference the title and topic name
    const dialogMessage = screen.getByText(/Remove "Attention Is All You Need" from "nlp"\?/)
    expect(dialogMessage).toBeInTheDocument()
    // Should NOT reference the arxiv_id in the dialog message
    expect(dialogMessage.textContent).not.toContain('2401.12345v1')
  })

  it('calls onRemove when confirm is clicked', async () => {
    const onRemove = vi.fn()
    render(
      <PaperDetail
        paper={PAPER}
        topicName="nlp"
        onRemove={onRemove}
        onClose={() => {}}
      />
    )
    await userEvent.click(screen.getByText('Remove from topic'))
    await userEvent.click(screen.getByText('Remove'))
    expect(onRemove).toHaveBeenCalledWith('2401.12345v1')
  })

  it('does not call onRemove when cancel is clicked', async () => {
    const onRemove = vi.fn()
    render(
      <PaperDetail
        paper={PAPER}
        topicName="nlp"
        onRemove={onRemove}
        onClose={() => {}}
      />
    )
    await userEvent.click(screen.getByText('Remove from topic'))
    await userEvent.click(screen.getByText('Cancel'))
    expect(onRemove).not.toHaveBeenCalled()
    // Dialog should be dismissed
    expect(screen.queryByText('Remove paper')).not.toBeInTheDocument()
  })
})
