import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import CitationReport from '../CitationReport'
import type { PaperReport } from '../../types'

const defaultProps = {
  checking: false,
  progress: null,
  report: null as PaperReport[] | null,
  error: null as string | null,
  onClose: vi.fn(),
}

const verifiedPaper: PaperReport = {
  arxiv_id: '2112.02989v1',
  title: 'On the complexity of Dark Chinese Chess',
  arxiv_url: 'https://arxiv.org/abs/2112.02989',
  total_citations: 2,
  verified_count: 2,
  unresolved_count: 0,
  mismatch_count: 0,
  has_issues: false,
  group: 'verified',
  mismatches: [],
  llm_phrases: [],
  topical_issues: [],
  sources: {},
}

const unverifiablePaper: PaperReport = {
  arxiv_id: '1806.00683v2',
  title: 'Deep Pepper',
  arxiv_url: 'https://arxiv.org/abs/1806.00683',
  total_citations: 28,
  verified_count: 8,
  unresolved_count: 20,
  mismatch_count: 0,
  has_issues: false,
  group: 'unverifiable',
  mismatches: [],
  llm_phrases: [],
  topical_issues: [],
  sources: {},
}

const issuePaper: PaperReport = {
  arxiv_id: '1909.10413v1',
  title: 'Automated Chess Commentator',
  arxiv_url: 'https://arxiv.org/abs/1909.10413',
  total_citations: 33,
  verified_count: 4,
  unresolved_count: 23,
  mismatch_count: 2,
  has_issues: true,
  group: 'issues',
  mismatches: [
    {
      key: 'DBLP:conf/icml/CollobertW08',
      message: 'arXiv ID 0156.13901 does not exist',
      severity: 'error',
      arxiv_url: null,
    },
    {
      key: 'DBLP:journals/corr/abs-1811-06031',
      message: 'Cites "A Hierarchical..." but actual is "A Hierarchical..."',
      severity: 'warning',
      arxiv_url: 'https://arxiv.org/abs/1811.06031v2',
    },
  ],
  llm_phrases: [],
  topical_issues: [],
  sources: {},
}

describe('CitationReport', () => {
  it('renders nothing when not checking and no report', () => {
    const { container } = render(<CitationReport {...defaultProps} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows "Starting citation check..." when checking with no progress', () => {
    render(<CitationReport {...defaultProps} checking={true} />)
    expect(screen.getByText('Starting citation check...')).toBeInTheDocument()
  })

  it('shows progress bar when checking with progress', () => {
    render(
      <CitationReport {...defaultProps} checking={true} progress={{ current: 3, total: 10 }} />
    )
    expect(screen.getByText(/3\/10/)).toBeInTheDocument()
  })

  it('shows error message when error is set', () => {
    render(
      <CitationReport
        {...defaultProps}
        checking={false}
        error="Unknown message type: check_citations"
      />
    )
    expect(screen.getByText('Unknown message type: check_citations')).toBeInTheDocument()
  })

  it('shows error even while checking flag is still true', () => {
    render(
      <CitationReport
        {...defaultProps}
        checking={true}
        error="Something went wrong"
      />
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.queryByText('Starting citation check...')).not.toBeInTheDocument()
  })

  it('shows disclaimer in bold red', () => {
    render(<CitationReport {...defaultProps} report={[verifiedPaper]} />)
    expect(screen.getByText(/DISCLAIMER/)).toBeInTheDocument()
    const disclaimer = screen.getByText(/DISCLAIMER/)
    expect(disclaimer.classList.contains('font-bold')).toBe(true)
    expect(disclaimer.classList.contains('text-red')).toBe(true)
  })

  it('groups verified papers at the top', () => {
    render(<CitationReport {...defaultProps} report={[verifiedPaper, issuePaper]} />)
    expect(screen.getByText(/All citations verified/)).toBeInTheDocument()
    expect(screen.getByText('On the complexity of Dark Chinese Chess')).toBeInTheDocument()
  })

  it('groups unverifiable papers separately', () => {
    render(<CitationReport {...defaultProps} report={[unverifiablePaper]} />)
    expect(screen.getByText(/Some citations could not be checked/)).toBeInTheDocument()
    expect(screen.getByText('Deep Pepper')).toBeInTheDocument()
  })

  it('shows issue details with mismatches', () => {
    render(<CitationReport {...defaultProps} report={[issuePaper]} />)
    expect(screen.getByText(/Potential issues detected/)).toBeInTheDocument()
    expect(screen.getByText('Automated Chess Commentator')).toBeInTheDocument()
    expect(screen.getByText(/0156\.13901 does not exist/)).toBeInTheDocument()
  })

  it('uses red style for error severity mismatches', () => {
    render(<CitationReport {...defaultProps} report={[issuePaper]} />)
    // The border class is on the outer div with border-l-2
    const errorText = screen.getByText(/0156\.13901/)
    const borderEl = errorText.closest('.border-l-2')
    expect(borderEl?.className).toContain('border-red')
  })

  it('uses amber style for warning severity mismatches', () => {
    render(<CitationReport {...defaultProps} report={[issuePaper]} />)
    const warningText = screen.getByText(/Hierarchical/)
    const borderEl = warningText.closest('.border-l-2')
    expect(borderEl?.className).toContain('border-amber')
  })

  it('shows zero citation warning', () => {
    const zeroPaper: PaperReport = {
      ...verifiedPaper,
      arxiv_id: '1510.08155v1',
      title: 'Chess Billiards',
      total_citations: 0,
      verified_count: 0,
      has_issues: true,
      group: 'issues',
    }
    render(<CitationReport {...defaultProps} report={[zeroPaper]} />)
    expect(screen.getByText(/No citations could be extracted/)).toBeInTheDocument()
  })

  it('renders arXiv links', () => {
    render(<CitationReport {...defaultProps} report={[verifiedPaper]} />)
    const links = screen.getAllByRole('link', { name: 'arXiv' })
    expect(links.length).toBeGreaterThan(0)
    expect(links[0]).toHaveAttribute('href', verifiedPaper.arxiv_url)
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(<CitationReport {...defaultProps} checking={true} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onClose).toHaveBeenCalled()
  })
})
