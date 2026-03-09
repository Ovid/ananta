import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TopicSidebar from '../TopicSidebar'
import type { TopicInfo, DocumentItem } from '../../types'

const mockTopics: TopicInfo[] = [
  { name: 'chess', document_count: 2, size: '1.0 MB', project_id: 'p1' },
  { name: 'math', document_count: 1, size: '0.5 MB', project_id: 'p2' },
]

const chessDocs: DocumentItem[] = [
  { id: 'doc-1', label: 'Chess Strategies', sublabel: 'A. Author' },
  { id: 'doc-2', label: 'Opening Theory', sublabel: 'B. Writer' },
]

const mathDocs: DocumentItem[] = [
  { id: 'doc-3', label: 'Algebra Basics' },
]

function defaultProps(overrides: Partial<Parameters<typeof TopicSidebar>[0]> = {}) {
  return {
    activeTopic: null as string | null,
    onSelectTopic: vi.fn(),
    onTopicsChange: vi.fn(),
    refreshKey: 0,
    selectedDocuments: new Set<string>(),
    onSelectionChange: vi.fn(),
    onDocumentClick: vi.fn(),
    onDocumentsLoaded: vi.fn(),
    loadDocuments: vi.fn().mockResolvedValue([]),
    loadTopics: vi.fn().mockResolvedValue(mockTopics),
    createTopic: vi.fn().mockResolvedValue(undefined),
    renameTopic: vi.fn().mockResolvedValue(undefined),
    deleteTopic: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('TopicSidebar (shared)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders topics loaded via loadTopics', async () => {
    const props = defaultProps()
    render(<TopicSidebar {...props} />)

    expect(await screen.findByText('chess')).toBeInTheDocument()
    expect(screen.getByText('math')).toBeInTheDocument()
    expect(props.loadTopics).toHaveBeenCalled()
  })

  it('shows empty state when no topics exist', async () => {
    const props = defaultProps({ loadTopics: vi.fn().mockResolvedValue([]) })
    render(<TopicSidebar {...props} />)

    expect(await screen.findByText(/No topics yet/)).toBeInTheDocument()
  })

  it('expands topic and loads documents via loadDocuments', async () => {
    const props = defaultProps({
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    const topicRow = await screen.findByText('chess')
    // Click the expand arrow
    const expandBtn = topicRow.closest('div')!.querySelector('button')!
    await userEvent.click(expandBtn)

    expect(await screen.findByText('Chess Strategies')).toBeInTheDocument()
    expect(screen.getByText('Opening Theory')).toBeInTheDocument()
    expect(props.loadDocuments).toHaveBeenCalledWith('chess')
  })

  it('calls onDocumentsLoaded when documents are loaded', async () => {
    const props = defaultProps({
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    const topicRow = await screen.findByText('chess')
    const expandBtn = topicRow.closest('div')!.querySelector('button')!
    await userEvent.click(expandBtn)

    await screen.findByText('Chess Strategies')
    expect(props.onDocumentsLoaded).toHaveBeenCalledWith(chessDocs)
  })

  it('calls onDocumentClick when document label is clicked', async () => {
    const props = defaultProps({
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    const topicRow = await screen.findByText('chess')
    const expandBtn = topicRow.closest('div')!.querySelector('button')!
    await userEvent.click(expandBtn)

    const docLabel = await screen.findByText('Chess Strategies')
    await userEvent.click(docLabel)

    expect(props.onDocumentClick).toHaveBeenCalledWith(chessDocs[0])
  })

  it('selects topic when document clicked in non-active topic', async () => {
    const props = defaultProps({
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    const topicRow = await screen.findByText('chess')
    const expandBtn = topicRow.closest('div')!.querySelector('button')!
    await userEvent.click(expandBtn)

    const docLabel = await screen.findByText('Chess Strategies')
    await userEvent.click(docLabel)

    expect(props.onSelectTopic).toHaveBeenCalledWith('chess')
  })

  it('does not call onSelectTopic when document clicked in already-active topic', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    // activeTopic triggers auto-expand + load
    const docLabel = await screen.findByText('Chess Strategies')
    await userEvent.click(docLabel)

    expect(props.onSelectTopic).not.toHaveBeenCalled()
    expect(props.onDocumentClick).toHaveBeenCalled()
  })

  it('toggles document selection via checkbox', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const checkboxes = screen.getAllByRole('checkbox')
    await userEvent.click(checkboxes[0])

    expect(props.onSelectionChange).toHaveBeenCalledWith(new Set(['doc-1']))
  })

  it('unchecks document when already selected', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      selectedDocuments: new Set(['doc-1', 'doc-2']),
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const checkboxes = screen.getAllByRole('checkbox')
    // Uncheck doc-1
    await userEvent.click(checkboxes[0])

    expect(props.onSelectionChange).toHaveBeenCalledWith(new Set(['doc-2']))
  })

  describe('cross-topic selection scoping', () => {
    it('"All" button adds current topic docs to selection, preserving other selections', async () => {
      // doc-3 is from math topic, already selected
      const props = defaultProps({
        activeTopic: 'chess',
        selectedDocuments: new Set(['doc-3']),
        loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      })
      render(<TopicSidebar {...props} />)

      const allBtn = await screen.findByRole('button', { name: 'All' })
      await userEvent.click(allBtn)

      // Should have doc-3 (preserved) + doc-1, doc-2 (added)
      expect(props.onSelectionChange).toHaveBeenCalledWith(new Set(['doc-3', 'doc-1', 'doc-2']))
    })

    it('"None" button removes only current topic docs from selection', async () => {
      // doc-1, doc-2 from chess; doc-3 from math
      const props = defaultProps({
        activeTopic: 'chess',
        selectedDocuments: new Set(['doc-1', 'doc-2', 'doc-3']),
        loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      })
      render(<TopicSidebar {...props} />)

      const noneBtn = await screen.findByRole('button', { name: 'None' })
      await userEvent.click(noneBtn)

      // Should only have doc-3 remaining (math topic preserved)
      expect(props.onSelectionChange).toHaveBeenCalledWith(new Set(['doc-3']))
    })
  })

  it('creates a topic via createTopic prop', async () => {
    const props = defaultProps()
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    const createBtn = screen.getByTitle('Create topic')
    await userEvent.click(createBtn)

    const input = screen.getByPlaceholderText('Topic name...')
    await userEvent.type(input, 'physics{Enter}')

    expect(props.createTopic).toHaveBeenCalledWith('physics')
  })

  it('deletes a topic via deleteTopic prop', async () => {
    const props = defaultProps()
    render(<TopicSidebar {...props} />)

    const topicRow = await screen.findByText('chess')
    // Hover to show menu button, then click it
    const menuBtn = topicRow.closest('div')!.querySelector('button:last-of-type')!
    // The menu button is the ... (ellipsis) button
    const groupDiv = topicRow.closest('[class*="group"]')!
    const buttons = within(groupDiv as HTMLElement).getAllByRole('button')
    // Last button is the menu (ellipsis)
    await userEvent.click(buttons[buttons.length - 1])

    const deleteBtn = await screen.findByText('Delete')
    await userEvent.click(deleteBtn)

    // Confirm dialog should appear
    const confirmBtn = await screen.findByRole('button', { name: 'Delete' })
    await userEvent.click(confirmBtn)

    expect(props.deleteTopic).toHaveBeenCalledWith('chess')
  })

  it('auto-expands and loads documents when activeTopic changes', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    expect(await screen.findByText('Chess Strategies')).toBeInTheDocument()
    expect(props.loadDocuments).toHaveBeenCalledWith('chess')
  })

  it('shows document count in topic row', async () => {
    const props = defaultProps()
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    // Should show "2 · 1.0 MB" for chess topic
    expect(screen.getByText(/2.*1\.0 MB/)).toBeInTheDocument()
  })

  it('shows selected/total count when some documents are selected', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      selectedDocuments: new Set(['doc-1']),
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    // Should show "1/2 · 1.0 MB" indicating 1 of 2 selected
    expect(screen.getByText(/1\/2.*1\.0 MB/)).toBeInTheDocument()
  })

  it('renders uncategorized docs section when provided', async () => {
    const uncatDocs: DocumentItem[] = [
      { id: 'uncat-1', label: 'Orphan Document' },
    ]
    const props = defaultProps({
      uncategorizedDocs: uncatDocs,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    expect(screen.getByText('Uncategorized')).toBeInTheDocument()
    expect(screen.getByText('Orphan Document')).toBeInTheDocument()
  })

  it('renders custom addButton when provided', async () => {
    const props = defaultProps({
      addButton: <button>Add Repo</button>,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    expect(screen.getByRole('button', { name: 'Add Repo' })).toBeInTheDocument()
  })

  it('passes style to the aside element', async () => {
    const props = defaultProps({ style: { width: '300px' } })
    const { container } = render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    const aside = container.querySelector('aside')!
    expect(aside.style.width).toBe('300px')
  })

  it('does not render doc menu button when addDocToTopic is not provided', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    // No ellipsis menu buttons should exist on document rows
    expect(screen.queryAllByTitle('Document actions')).toHaveLength(0)
  })

  it('renders doc menu button when addDocToTopic is provided', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      addDocToTopic: vi.fn(),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    // Each doc row should have an ellipsis menu button
    const menuButtons = screen.getAllByTitle('Document actions')
    expect(menuButtons.length).toBeGreaterThanOrEqual(2) // 2 chess docs
  })

  it('shows "Add to..." submenu with available topics when doc menu is clicked', async () => {
    const addDocToTopic = vi.fn()
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      addDocToTopic,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    await userEvent.click(menuButtons[0])

    // Should show "Add to..." menu item but not "Remove from" (removeDocFromTopic not provided)
    expect(screen.getByText('Add to\u2026')).toBeInTheDocument()
    expect(screen.queryByText(/Remove from/)).not.toBeInTheDocument()
  })

  it('calls addDocToTopic when a topic is selected from submenu', async () => {
    const addDocToTopic = vi.fn().mockResolvedValue(undefined)
    const loadDocuments = vi.fn()
      .mockImplementation((name: string) =>
        Promise.resolve(name === 'chess' ? chessDocs : [])
      )
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments,
      addDocToTopic,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    await userEvent.click(menuButtons[0])
    await userEvent.click(screen.getByText('Add to\u2026'))
    // "math" appears both in sidebar topic list and in submenu; pick the submenu button
    const mathButtons = screen.getAllByRole('button', { name: 'math' })
    await userEvent.click(mathButtons[0])

    await waitFor(() => {
      expect(addDocToTopic).toHaveBeenCalledWith('doc-1', 'math')
    })
  })

  it('shows "Remove from [topic]" for docs inside a topic and calls removeDocFromTopic', async () => {
    const removeDocFromTopic = vi.fn().mockResolvedValue(undefined)
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      addDocToTopic: vi.fn(),
      removeDocFromTopic,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    await userEvent.click(menuButtons[0])

    const removeBtn = screen.getByText('Remove from chess')
    await userEvent.click(removeBtn)

    expect(removeDocFromTopic).toHaveBeenCalledWith('doc-1', 'chess')
  })

  it('shows doc actions button when only removeDocFromTopic is provided', async () => {
    const removeDocFromTopic = vi.fn().mockResolvedValue(undefined)
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      removeDocFromTopic,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    expect(menuButtons.length).toBeGreaterThan(0)
  })

  it('renders doc menu on uncategorized docs with only "Add to..." (no remove)', async () => {
    const addDocToTopic = vi.fn().mockResolvedValue(undefined)
    const uncatDocs: DocumentItem[] = [
      { id: 'uncat-1', label: 'Orphan Doc' },
    ]
    const props = defaultProps({
      uncategorizedDocs: uncatDocs,
      addDocToTopic,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess') // wait for topics to load
    const menuBtn = screen.getByTitle('Document actions')
    await userEvent.click(menuBtn)

    expect(screen.getByText('Add to\u2026')).toBeInTheDocument()
    expect(screen.queryByText(/Remove from/)).not.toBeInTheDocument()
  })

  it('shows "View" option in doc menu that calls onDocumentClick', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      addDocToTopic: vi.fn(),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    await userEvent.click(menuButtons[0])

    const viewBtn = screen.getByText('View')
    await userEvent.click(viewBtn)

    expect(props.onDocumentClick).toHaveBeenCalledWith(chessDocs[0])
  })

  it('shows "Delete" in doc menu for uncategorized doc when deleteDocument is provided', async () => {
    const deleteDocument = vi.fn().mockResolvedValue(undefined)
    const uncatDocs: DocumentItem[] = [
      { id: 'uncat-1', label: 'Orphan Doc' },
    ]
    const props = defaultProps({
      uncategorizedDocs: uncatDocs,
      addDocToTopic: vi.fn(),
      deleteDocument,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    const menuBtn = screen.getByTitle('Document actions')
    await userEvent.click(menuBtn)

    const deleteBtn = screen.getByRole('button', { name: 'Delete' })
    await userEvent.click(deleteBtn)

    // Confirm dialog should appear
    const confirmBtn = await screen.findByRole('button', { name: 'Delete' })
    await userEvent.click(confirmBtn)

    expect(deleteDocument).toHaveBeenCalledWith('uncat-1')
  })

  it('refreshes topics after document deletion', async () => {
    const deleteDocument = vi.fn().mockResolvedValue(undefined)
    const uncatDocs: DocumentItem[] = [
      { id: 'uncat-1', label: 'Orphan Doc' },
    ]
    const props = defaultProps({
      uncategorizedDocs: uncatDocs,
      addDocToTopic: vi.fn(),
      deleteDocument,
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('chess')
    const menuBtn = screen.getByTitle('Document actions')
    await userEvent.click(menuBtn)

    const deleteBtn = screen.getByRole('button', { name: 'Delete' })
    await userEvent.click(deleteBtn)

    const confirmBtn = await screen.findByRole('button', { name: 'Delete' })
    await userEvent.click(confirmBtn)

    await waitFor(() => {
      expect(deleteDocument).toHaveBeenCalledWith('uncat-1')
    })
    await waitFor(() => {
      expect(props.onTopicsChange).toHaveBeenCalled()
    })
  })

  it('does not show "Delete" in doc menu when deleteDocument is not provided', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      addDocToTopic: vi.fn(),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Chess Strategies')
    const menuButtons = screen.getAllByTitle('Document actions')
    await userEvent.click(menuButtons[0])

    expect(screen.getByText('View')).toBeInTheDocument()
    // No "Delete" button should exist in the doc menu (only topic delete might exist)
    const buttons = screen.getAllByRole('button')
    const deleteInMenu = buttons.filter(b => b.textContent === 'Delete' && b.closest('.absolute'))
    expect(deleteInMenu).toHaveLength(0)
  })

  it('shows "View" option for uncategorized doc even when no topics exist', async () => {
    const props = defaultProps({
      loadTopics: vi.fn().mockResolvedValue([]),
      uncategorizedDocs: [{ id: 'uncat-1', label: 'Orphan Doc' }],
      addDocToTopic: vi.fn(),
    })
    render(<TopicSidebar {...props} />)

    await screen.findByText('Orphan Doc')
    const menuBtn = screen.getByTitle('Document actions')
    await userEvent.click(menuBtn)

    expect(screen.getByText('View')).toBeInTheDocument()
  })

  it('excludes topic from "Add to..." when a doc with the same label already exists there', async () => {
    // "chess" topic already has "Chess Strategies" (doc-1)
    // An uncategorized doc with a different id but the same label should NOT be eligible for chess
    const addDocToTopic = vi.fn().mockResolvedValue(undefined)
    const uncatDocs: DocumentItem[] = [
      { id: 'doc-99', label: 'Chess Strategies' },
    ]
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
      uncategorizedDocs: uncatDocs,
      addDocToTopic,
    })
    render(<TopicSidebar {...props} />)

    // Wait for chess topic docs to load
    await screen.findByText('Opening Theory')
    // Find the uncategorized doc's menu button
    const uncatSection = screen.getByText('Uncategorized').closest('div')!.parentElement!
    const menuBtn = within(uncatSection as HTMLElement).getByTitle('Document actions')
    await userEvent.click(menuBtn)

    // "Add to..." shows (math is still eligible — docs not loaded)
    await userEvent.click(screen.getByText('Add to\u2026'))

    // "math" should appear as eligible, but "chess" should NOT (same-label doc already there)
    const submenuButtons = screen.getAllByRole('button').filter(
      b => b.textContent === 'math' || b.textContent === 'chess'
    )
    const labels = submenuButtons.map(b => b.textContent)
    expect(labels).toContain('math')
    expect(labels).not.toContain('chess')
  })

  it('reloads documents for expanded topic when refreshKey changes', async () => {
    const loadDocuments = vi.fn().mockResolvedValue(chessDocs)
    const props = defaultProps({
      activeTopic: 'chess',
      loadDocuments,
    })
    const { rerender } = render(<TopicSidebar {...props} />)

    // Documents load on initial render
    expect(await screen.findByText('Chess Strategies')).toBeInTheDocument()
    expect(loadDocuments).toHaveBeenCalledWith('chess')
    loadDocuments.mockClear()

    // Simulate refreshKey change (e.g., after adding a doc to a topic)
    const updatedDocs: DocumentItem[] = [
      ...chessDocs,
      { id: 'doc-new', label: 'New Chess Book' },
    ]
    loadDocuments.mockResolvedValue(updatedDocs)
    rerender(<TopicSidebar {...props} refreshKey={1} />)

    // Documents should reload and show the new doc
    expect(await screen.findByText('New Chess Book')).toBeInTheDocument()
    expect(loadDocuments).toHaveBeenCalledWith('chess')
  })

  it('shows viewing highlight on the document with viewingDocumentId', async () => {
    const props = defaultProps({
      activeTopic: 'chess',
      viewingDocumentId: 'doc-1',
      loadDocuments: vi.fn().mockResolvedValue(chessDocs),
    })
    render(<TopicSidebar {...props} />)

    const docLabel = await screen.findByText('Chess Strategies')
    const docRow = docLabel.closest('div[class*="flex"]')!
    expect(docRow.className).toContain('accent')
  })
})
