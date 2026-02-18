# Repo-to-Topic Assignment via Context Menu

## Problem

Repos in "Uncategorized" (or already in one topic) have no UI to assign them to topics. Repos can belong to multiple topics, but the only way to associate a repo with a topic is during initial add via the AddRepoModal.

## Design

### Interaction Model

Each document row in the sidebar gets an ellipsis button (visible on hover) that opens a context menu:

- **Inside a topic:** "Add to..." submenu (topics the repo is NOT in) + "Remove from [Topic]"
- **In Uncategorized:** "Add to..." submenu (all topics). No remove option.

### Component Boundaries

TopicSidebar is a shared component used by both code-explorer and arxiv frontends. The feature is opt-in via two new optional callback props:

- `addDocToTopic?: (docId: string, topicName: string) => Promise<void>`
- `removeDocFromTopic?: (docId: string, topicName: string) => Promise<void>`

When absent, no ellipsis button renders — arxiv frontend is unaffected.

### Topic Membership Detection

The sidebar already maintains `topicDocs` state (loaded when a topic is expanded). We derive membership from this: if `topicDocs[topicName]` contains the doc ID, the repo is in that topic. For unexpanded topics, we conservatively show them in the "Add to..." list — the backend's `add_repo` is idempotent.

### Menu Styling

Same pattern as the existing topic-level context menu: absolute-positioned `bg-surface-2 border border-border rounded shadow-lg text-xs` dropdown. Ellipsis button uses existing `group`/`group-hover:opacity-100` hover-reveal pattern.

### Code-Explorer Wiring

App.tsx passes callbacks that call existing API endpoints:

- `addDocToTopic` → `api.topicRepos.add(topic, docId)` + bump `reposVersion`
- `removeDocFromTopic` → `api.topicRepos.remove(topic, docId)` + bump `reposVersion`

### Backend

No changes needed. `POST/DELETE /topics/{name}/repos/{projectId}` already exist in code-explorer's API.

### Files Changed

1. `shared/frontend/src/components/TopicSidebar.tsx` — new props, doc-level context menu in both `renderDocList` and uncategorized section
2. `shared/frontend/src/components/__tests__/TopicSidebar.test.tsx` — test menu appearance, callback invocation, opt-in behavior
3. `code_explorer/frontend/src/App.tsx` — wire new callbacks to API client
4. `code_explorer/frontend/src/__tests__/App.test.tsx` — verify callbacks passed
