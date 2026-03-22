import { useCallback, useRef, type CSSProperties, type ReactNode } from 'react'

import { TopicSidebar as SharedTopicSidebar } from '@ananta/shared-ui'
import type { TopicInfo, DocumentItem } from '@ananta/shared-ui'
import { api } from '../api/client'
import type { PaperInfo } from '../types'

interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
  refreshKey: number
  selectedPapers: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  onPaperClick: (paper: PaperInfo) => void
  onPapersLoaded: (papers: PaperInfo[]) => void
  viewingPaperId?: string | null
  style?: CSSProperties
  bottomControls?: ReactNode
}

function paperToDocument(paper: PaperInfo): DocumentItem {
  const sublabel = `${paper.authors[0] ?? ''} \u00B7 ${paper.date?.slice(0, 4) ?? ''}`
  return { id: paper.arxiv_id, label: paper.title, sublabel }
}

export default function TopicSidebar({
  activeTopic,
  onSelectTopic,
  onTopicsChange,
  refreshKey,
  selectedPapers,
  onSelectionChange,
  onPaperClick,
  onPapersLoaded,
  viewingPaperId,
  style,
  bottomControls,
}: TopicSidebarProps) {
  // Keep a lookup from document ID -> PaperInfo so we can reverse-map
  // in onDocumentClick and onDocumentsLoaded callbacks.
  const paperMapRef = useRef<Map<string, PaperInfo>>(new Map())

  const loadTopics = useCallback(async (): Promise<TopicInfo[]> => {
    return api.topics.list()
  }, [])

  const loadDocuments = useCallback(async (topicName: string): Promise<DocumentItem[]> => {
    const papers = await api.papers.list(topicName)
    for (const p of papers) {
      paperMapRef.current.set(p.arxiv_id, p)
    }
    return papers.map(paperToDocument)
  }, [])

  const handleDocumentClick = useCallback((doc: DocumentItem) => {
    const paper = paperMapRef.current.get(doc.id)
    if (paper) {
      onPaperClick(paper)
    }
  }, [onPaperClick])

  const handleDocumentsLoaded = useCallback((docs: DocumentItem[]) => {
    const papers = docs
      .map(d => paperMapRef.current.get(d.id))
      .filter((p): p is PaperInfo => p != null)
    onPapersLoaded(papers)
  }, [onPapersLoaded])

  const handleCreateTopic = useCallback(async (name: string) => {
    await api.topics.create(name)
  }, [])

  const handleRenameTopic = useCallback(async (oldName: string, newName: string) => {
    await api.topics.rename(oldName, newName)
  }, [])

  const handleDeleteTopic = useCallback(async (name: string) => {
    await api.topics.delete(name)
  }, [])

  const handleAddDocToTopic = useCallback(async (docId: string, topicName: string) => {
    await api.papers.add(docId, [topicName])
  }, [])

  const handleRemoveDocFromTopic = useCallback(async (docId: string, topicName: string) => {
    await api.papers.remove(topicName, docId)
  }, [])

  const handleRenameDocument = useCallback(async (docId: string, newName: string) => {
    await api.papers.rename(docId, newName)
  }, [])

  const handleReorderItems = useCallback(async (topicName: string, itemIds: string[]) => {
    await api.papers.reorder(topicName, itemIds)
  }, [])

  return (
    <SharedTopicSidebar
      activeTopic={activeTopic}
      onSelectTopic={onSelectTopic}
      onTopicsChange={onTopicsChange}
      refreshKey={refreshKey}
      selectedDocuments={selectedPapers}
      onSelectionChange={onSelectionChange}
      onDocumentClick={handleDocumentClick}
      onDocumentsLoaded={handleDocumentsLoaded}
      loadDocuments={loadDocuments}
      loadTopics={loadTopics}
      createTopic={handleCreateTopic}
      renameTopic={handleRenameTopic}
      deleteTopic={handleDeleteTopic}
      addDocToTopic={handleAddDocToTopic}
      removeDocFromTopic={handleRemoveDocFromTopic}
      renameDocument={handleRenameDocument}
      reorderItems={handleReorderItems}
      viewingDocumentId={viewingPaperId}
      style={style}
      bottomControls={bottomControls}
    />
  )
}
