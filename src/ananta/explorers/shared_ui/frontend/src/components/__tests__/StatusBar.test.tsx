import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import StatusBar from '../StatusBar'

describe('StatusBar', () => {
  const defaultProps = {
    topicName: 'my-topic',
    modelName: 'gpt-4',
    tokens: { prompt: 100, completion: 50, total: 150 },
    budget: null,
    phase: 'Ready',
    onModelClick: vi.fn(),
  }

  it('renders topic name', () => {
    render(<StatusBar {...defaultProps} />)
    expect(screen.getByText('my-topic')).toBeInTheDocument()
  })

  it('renders model name as clickable button', async () => {
    const onModelClick = vi.fn()
    render(<StatusBar {...defaultProps} onModelClick={onModelClick} />)
    await userEvent.click(screen.getByText('gpt-4'))
    expect(onModelClick).toHaveBeenCalledOnce()
  })

  it('renders token counts', () => {
    render(<StatusBar {...defaultProps} />)
    expect(screen.getByText('150')).toBeInTheDocument()
  })

  it('renders phase with status dot', () => {
    render(<StatusBar {...defaultProps} phase="Running" />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders dash when topicName is null', () => {
    render(<StatusBar {...defaultProps} topicName={null} />)
    // The em-dash fallback
    expect(screen.getByText('\u2014')).toBeInTheDocument()
  })

  it('renders context budget percentage', () => {
    render(
      <StatusBar
        {...defaultProps}
        budget={{ used_tokens: 5000, max_tokens: 10000, percentage: 50, level: 'green' }}
      />
    )
    expect(screen.getByText('Context: 50%')).toBeInTheDocument()
  })
})
