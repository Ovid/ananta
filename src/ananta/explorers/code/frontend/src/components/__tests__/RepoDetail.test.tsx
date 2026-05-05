import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import RepoDetail from '../RepoDetail'
import type { RepoInfo, RepoAnalysis } from '../../types'

const baseRepo: RepoInfo = {
  project_id: 'owner-myrepo',
  source_url: 'https://github.com/owner/myrepo',
  file_count: 42,
  analysis_status: 'current',
  display_name: null,
}

const sampleAnalysis: RepoAnalysis = {
  version: '1',
  generated_at: '2025-01-15T10:00:00Z',
  head_sha: 'abc123',
  overview: 'A web application framework for building REST APIs.',
  components: [
    {
      name: 'AuthModule',
      path: 'src/auth',
      description: 'Handles user authentication and authorization.',
      apis: [{ method: 'POST', path: '/login' }],
      models: ['User', 'Token'],
      entry_points: ['auth_router'],
      internal_dependencies: ['DatabaseModule'],
    },
  ],
  external_dependencies: [
    {
      name: 'fastapi',
      type: 'runtime',
      description: 'ASGI web framework',
      used_by: ['AuthModule', 'CoreModule'],
    },
  ],
  caveats: 'Some generated endpoints may not reflect runtime middleware.',
}

function renderDetail(overrides: {
  repo?: RepoInfo
  analysis?: RepoAnalysis | null
  analyzing?: boolean
  onClose?: () => void
  onAnalyze?: (id: string) => void
  onCheckUpdates?: (id: string) => void
  onRemove?: (id: string) => void
} = {}) {
  const props = {
    repo: baseRepo,
    analysis: sampleAnalysis as RepoAnalysis | null,
    analyzing: false,
    onClose: vi.fn(),
    onAnalyze: vi.fn(),
    onCheckUpdates: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  }
  return render(<RepoDetail {...props} />)
}

describe('RepoDetail', () => {
  it('renders repo project_id as heading', () => {
    renderDetail()
    expect(screen.getByRole('heading', { name: /owner-myrepo/ })).toBeInTheDocument()
  })

  it('renders source URL as a link', () => {
    renderDetail()
    const link = screen.getByRole('link', { name: /github\.com\/owner\/myrepo/i })
    expect(link).toHaveAttribute('href', 'https://github.com/owner/myrepo')
  })

  it('renders file count', () => {
    renderDetail()
    expect(screen.getByText(/42 files/)).toBeInTheDocument()
  })

  it('renders "not analyzed" badge when analysis_status is missing', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'missing' } })
    const badge = screen.getByText('not analyzed')
    expect(badge.className).toMatch(/red/)
  })

  it('renders "current" analysis status badge', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'current' } })
    const badge = screen.getByText('current')
    expect(badge.className).toMatch(/green/)
  })

  it('renders "stale" analysis status badge', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'stale' } })
    const badge = screen.getByText('stale')
    expect(badge.className).toMatch(/amber/)
  })

  it('shows "Generate Analysis" button when status is "missing"', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'missing' } })
    expect(screen.getByRole('button', { name: 'Generate Analysis' })).toBeInTheDocument()
  })

  it('shows "Regenerate Analysis" button when status is "stale"', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'stale' } })
    expect(screen.getByRole('button', { name: 'Regenerate Analysis' })).toBeInTheDocument()
  })

  it('hides generate button when status is "current"', () => {
    renderDetail({ repo: { ...baseRepo, analysis_status: 'current' } })
    expect(screen.queryByRole('button', { name: 'Generate Analysis' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Regenerate Analysis' })).not.toBeInTheDocument()
  })

  it('shows "No analysis available" message when analysis is null', () => {
    renderDetail({ analysis: null })
    expect(screen.getByText(/No analysis available/)).toBeInTheDocument()
  })

  it('shows analysis overview when analysis exists', () => {
    renderDetail()
    expect(screen.getByText('A web application framework for building REST APIs.')).toBeInTheDocument()
  })

  it('shows component name and path when analysis exists', () => {
    renderDetail()
    expect(screen.getByText('AuthModule')).toBeInTheDocument()
    expect(screen.getByText('src/auth')).toBeInTheDocument()
  })

  it('shows external dependency when analysis exists', () => {
    renderDetail()
    expect(screen.getByText('fastapi')).toBeInTheDocument()
    expect(screen.getByText('ASGI web framework')).toBeInTheDocument()
  })

  it('calls onAnalyze when "Generate Analysis" is clicked', async () => {
    const onAnalyze = vi.fn()
    renderDetail({
      repo: { ...baseRepo, analysis_status: 'missing' },
      onAnalyze,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Generate Analysis' }))
    expect(onAnalyze).toHaveBeenCalledWith('owner-myrepo')
  })

  it('shows "Analysis in progress…" message when analyzing prop is true', () => {
    renderDetail({
      repo: { ...baseRepo, analysis_status: 'missing' },
      analysis: null,
      analyzing: true,
    })
    expect(screen.getByText(/analysis in progress/i)).toBeInTheDocument()
    expect(screen.queryByText(/no analysis available/i)).not.toBeInTheDocument()
  })

  it('hides Generate Analysis, Check for Updates, and Remove buttons while analyzing', () => {
    renderDetail({
      repo: { ...baseRepo, analysis_status: 'missing' },
      analysis: null,
      analyzing: true,
    })
    expect(screen.queryByRole('button', { name: 'Generate Analysis' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /analyzing/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check for Updates' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
  })

  it('still shows the close button while analyzing (so user can navigate away)', () => {
    renderDetail({
      repo: { ...baseRepo, analysis_status: 'missing' },
      analysis: null,
      analyzing: true,
    })
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument()
  })

  it('calls onCheckUpdates when "Check for Updates" is clicked', async () => {
    const onCheckUpdates = vi.fn()
    renderDetail({ onCheckUpdates })
    await userEvent.click(screen.getByRole('button', { name: 'Check for Updates' }))
    expect(onCheckUpdates).toHaveBeenCalledWith('owner-myrepo')
  })

  it('disables button and shows "Checking…" while update check runs', async () => {
    let resolveCheck!: () => void
    const onCheckUpdates = vi.fn(() => new Promise<void>(r => { resolveCheck = r }))
    renderDetail({ onCheckUpdates })
    await userEvent.click(screen.getByRole('button', { name: 'Check for Updates' }))
    // While the promise is pending, button should show loading state
    const btn = screen.getByRole('button', { name: /checking/i })
    expect(btn).toBeDisabled()
    // Resolve the promise and verify button restores
    await act(async () => { resolveCheck() })
    expect(screen.getByRole('button', { name: 'Check for Updates' })).toBeEnabled()
  })

  it('calls onRemove when "Remove" is clicked', async () => {
    const onRemove = vi.fn()
    renderDetail({ onRemove })
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onRemove).toHaveBeenCalledWith('owner-myrepo')
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    renderDetail({ onClose })
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
