import { useCallback, useRef, type CSSProperties } from 'react'

import { TopicSidebar as SharedTopicSidebar } from '@shesha/shared-ui'
import type { TopicInfo as SharedTopicInfo, DocumentItem } from '@shesha/shared-ui'
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
}: TopicSidebarProps) {
  // Keep a lookup from document ID -> PaperInfo so we can reverse-map
  // in onDocumentClick and onDocumentsLoaded callbacks.
  const paperMapRef = useRef<Map<string, PaperInfo>>(new Map())

  const loadTopics = useCallback(async (): Promise<SharedTopicInfo[]> => {
    const topics = await api.topics.list()
    return topics.map(t => ({
      name: t.name,
      document_count: t.paper_count,
      size: t.size,
      project_id: t.project_id,
    }))
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
      viewingDocumentId={viewingPaperId}
      style={style}
    />
  )
}
