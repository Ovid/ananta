# Design Document: Explorer More Button

## Overview

This feature adds a "More" button to the shared ChatArea component that enables users to request deeper analysis with a single click. The button automatically sends a predefined prompt asking the system to verify and enhance its previous response.

The implementation leverages the existing shared component architecture to ensure all three explorers (arXiv, code, and document) inherit the functionality without additional configuration. The More button integrates seamlessly with the existing WebSocket-based message flow and respects the same state management constraints as the Send button.

### Key Design Principles

1. **Shared Component Pattern**: Implement once in ChatArea.tsx, inherit everywhere
2. **Consistency**: Mirror the Send button's behavior and state management
3. **Minimal Disruption**: Reuse existing WebSocket infrastructure and state hooks
4. **User Experience**: Provide immediate visual feedback and maintain conversation flow
5. **Accessibility**: Ensure full keyboard navigation and screen reader support

## Architecture

### Component Hierarchy

```
ChatArea (shared component)
├── Message Display Area
│   ├── Exchange History
│   ├── Pending Question
│   └── Thinking Indicator
└── Input Area
    ├── Textarea (prompt input)
    ├── More Button (NEW)
    ├── Send/Cancel Button
    └── Clear History Button
```

### State Flow

```
User clicks More button
    ↓
ChatArea validates state (connected, hasDocuments, hasTopic, !thinking)
    ↓
ChatArea sends predefined prompt via wsSend
    ↓
ChatArea updates local state (thinking=true, pendingQuestion=prompt)
    ↓
WebSocket messages update phase/status
    ↓
Complete message triggers history reload
    ↓
ChatArea displays updated conversation
```

### Integration Points

1. **WebSocket Layer**: Uses existing `wsSend` prop to transmit query messages
2. **State Management**: Shares `thinking`, `pendingQuestion`, and `phase` state with Send button
3. **History Management**: Triggers same `loadHistory` callback on completion
4. **Error Handling**: Uses same error toast mechanism as existing queries

## Components and Interfaces

### Modified Component: ChatArea

**Location**: `src/shesha/experimental/shared/frontend/src/components/ChatArea.tsx`

**New State**: None (reuses existing state variables)

**New Props**: None (uses existing props)

**New Constants**:
```typescript
const DEEPER_ANALYSIS_PROMPT = "Do a deeper dive to verify if your report is complete, accurate, and relevant. Explain any changes or additions in bullet points and then present the full report with those changes and/or additions. You must also walk through the entire report, point by point, and ensure its aligned with the previous report and the changes or additions."
```

**New Handler**:
```typescript
const handleMore = useCallback(() => {
  if (!canSendMore || !selectedDocuments) return
  const question = DEEPER_ANALYSIS_PROMPT
  const msg: Record<string, unknown> = { 
    type: 'query', 
    topic: topicName, 
    question, 
    document_ids: Array.from(selectedDocuments) 
  }
  wsSend(msg)
  setInput('') // Clear any existing input
  setPendingQuestion(question)
  setPendingSentAt(new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
  setThinking(true)
  setPhase('Starting')
}, [topicName, wsSend, selectedDocuments])
```

**New Computed Value**:
```typescript
const canSendMore = !!topicName && !thinking && connected && hasDocuments
```

**UI Changes**:
The More button will be inserted between the textarea and the Send/Cancel button:

```tsx
<div className="flex gap-2">
  <textarea {...existingProps} />
  
  {/* NEW: More button */}
  {!thinking && (
    <button
      onClick={handleMore}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleMore()
        }
      }}
      disabled={!canSendMore}
      aria-label="Request deeper analysis"
      aria-disabled={!canSendMore}
      className="px-4 py-2 bg-surface-2 border border-border text-text-primary rounded text-sm font-medium hover:bg-surface-3 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
    >
      More
    </button>
  )}
  
  {thinking ? (
    <button {...cancelButtonProps}>Cancel</button>
  ) : (
    <button {...sendButtonProps}>Send</button>
  )}
  
  <button {...clearButtonProps}>🗑️</button>
</div>
```

### Styling Approach

The More button uses neutral styling (surface-2 background, border) to differentiate it from the primary action Send button (accent background) while maintaining visual consistency with the overall design system.

**Color Palette Reference** (from existing ChatArea):
- Primary action (Send): `bg-accent text-surface-0`
- Secondary action (More): `bg-surface-2 border border-border text-text-primary`
- Destructive action (Cancel): `bg-red text-white`
- Disabled state: `opacity-30 cursor-not-allowed`
- Focus indicator: `focus:ring-2 focus:ring-accent focus:ring-offset-2`

### Accessibility Implementation

The More button implements comprehensive accessibility features to ensure usability for all users:

**Keyboard Navigation:**
- Natural tab order: textarea → More button → Send/Cancel button → Clear button
- Keyboard activation via Enter or Space key (handled by `onKeyDown` handler)
- Visible focus indicator using Tailwind's focus ring utilities

**Screen Reader Support:**
- `aria-label="Request deeper analysis"` provides clear purpose description
- `aria-disabled` attribute reflects button state (mirrors `disabled` prop)
- Button text "More" is announced along with the aria-label
- Disabled state is announced by screen readers

**Visual Accessibility:**
- Focus ring with 2px width and accent color for high visibility
- Ring offset ensures focus indicator doesn't overlap button border
- Disabled state uses 30% opacity for clear visual distinction
- Cursor changes to `not-allowed` when disabled

**Implementation Notes:**
- The `onKeyDown` handler explicitly handles Enter and Space to ensure consistent behavior across browsers
- `e.preventDefault()` prevents default button behavior (form submission) when using Space key
- Focus styles use `focus:outline-none` to remove default outline and replace with custom ring for consistency

## Data Models

### WebSocket Message Structure

The More button sends the same message structure as the Send button:

```typescript
{
  type: 'query',
  topic: string,           // Current topic name
  question: string,        // DEEPER_ANALYSIS_PROMPT constant
  document_ids: string[]   // Array from selectedDocuments Set
}
```

### State Variables (Existing, Reused)

```typescript
thinking: boolean              // Disables More button when true
pendingQuestion: string | null // Displays the prompt in chat
pendingSentAt: string         // Timestamp for display
phase: string                 // Status updates during processing
topicName: string | null      // Required for sending
selectedDocuments: Set<string> | undefined // Required for sending
connected: boolean            // WebSocket connection state
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Button Enablement Preconditions

*For any* ChatArea component state, the More button SHALL be enabled if and only if all of the following conditions are true: WebSocket is connected, at least one document is selected, a topic is selected, and the system is not currently thinking.

**Validates: Requirements 2.1, 2.2, 2.4, 2.5**

### Property 2: Message Transmission

*For any* valid More button click (when button is enabled), the ChatArea SHALL call wsSend with a message containing type='query', the current topic name, the deeper analysis prompt as the question, and the array of selected document IDs.

**Validates: Requirements 3.1, 4.3**

### Property 3: Textarea Clearing

*For any* More button click, regardless of the current textarea content (empty or non-empty), the ChatArea SHALL clear the textarea input after sending the message.

**Validates: Requirements 3.3**

### Property 4: Thinking State Activation

*For any* More button click, the ChatArea SHALL set the thinking state to true, which disables further queries and displays the thinking indicator.

**Validates: Requirements 3.4**

### Property 5: Pending Question Display

*For any* More button click, the ChatArea SHALL set the pendingQuestion state to the deeper analysis prompt text, causing it to be displayed in the chat message area.

**Validates: Requirements 3.5**

### Property 6: Keyboard Activation

*For any* More button that has focus, when the user presses Enter or Space key, the ChatArea SHALL trigger the same handleMore function as a mouse click would.

**Validates: Requirements 6.3**

### Example-Based Tests

The following behaviors should be verified with specific example tests rather than property-based tests:

1. **UI Structure** (Req 1.1, 1.2, 1.4): Verify the More button is positioned between textarea and Send button, displays "More" text, and is present in the DOM when ChatArea renders.

2. **Prompt Constant** (Req 3.2): Verify the DEEPER_ANALYSIS_PROMPT constant equals the exact specified text.

3. **Button Visibility During Thinking** (Req 2.3): Verify the More button is not rendered when thinking=true (replaced by Cancel button).

4. **Explorer Integration** (Req 4.2): Verify all three explorers (arXiv, code, document) render the More button when using ChatArea.

5. **Existing Behavior Preservation** (Req 5.1, 5.3, 5.4): Verify that clicking More triggers the same visual feedback, history reload, and error handling as the Send button.

6. **Accessibility Attributes** (Req 6.1, 6.2, 6.4, 6.5, 6.6): Verify the More button has correct tab order, focus indicator, aria-label, and aria-disabled attributes.


## Error Handling

The More button leverages the existing error handling infrastructure in ChatArea. No new error handling logic is required.

### Existing Error Scenarios

1. **WebSocket Disconnection**: The More button is automatically disabled when `connected=false`. If disconnection occurs during processing, the existing WebSocket error handler displays a toast and resets state.

2. **Query Processing Errors**: If the RLM engine encounters an error while processing the deeper analysis request, the WebSocket sends an error message (`type: 'error'`), which triggers the existing error handler to display a toast and reset the thinking state.

3. **Network Errors**: WebSocket-level network errors are handled by the existing WebSocket infrastructure, which attempts reconnection and updates the `connected` state accordingly.

4. **Invalid State**: The More button is disabled when preconditions aren't met (no topic, no documents, already thinking), preventing invalid queries from being sent.

### Error Recovery

All error scenarios result in the same recovery flow:
1. Display error toast message to user
2. Reset `thinking` state to false
3. Clear `pendingQuestion` and `phase` state
4. Re-enable the More button (if other preconditions are met)

This ensures users can retry their request after addressing any issues.

## Testing Strategy

### Unit Testing Approach

Unit tests will focus on specific examples, edge cases, and component behavior verification. Tests will use React Testing Library and Vitest.

**Test Categories:**

1. **Rendering Tests**
   - Verify More button is rendered with correct text
   - Verify button positioning in the DOM structure
   - Verify button is present when ChatArea renders with valid props

2. **State-Based Enablement Tests**
   - Verify button is disabled when connected=false
   - Verify button is disabled when selectedDocuments is undefined
   - Verify button is disabled when selectedDocuments is empty Set
   - Verify button is disabled when topicName is null
   - Verify button is disabled when thinking=true
   - Verify button is enabled when all preconditions are met

3. **Click Behavior Tests**
   - Verify clicking More calls wsSend with correct message structure
   - Verify clicking More clears textarea content
   - Verify clicking More sets thinking=true
   - Verify clicking More sets pendingQuestion to prompt text
   - Verify clicking More sets pendingSentAt timestamp

4. **Integration Tests**
   - Verify More button appears in arXiv explorer
   - Verify More button appears in code explorer
   - Verify More button appears in document explorer
   - Verify More button uses same wsSend prop as Send button

5. **Constant Verification**
   - Verify DEEPER_ANALYSIS_PROMPT constant has exact specified text

6. **Accessibility Tests**
   - Verify More button is reachable via Tab key navigation
   - Verify More button displays focus indicator when focused
   - Verify More button has aria-label attribute
   - Verify More button has aria-disabled attribute matching disabled state
   - Verify Enter key activates More button when focused
   - Verify Space key activates More button when focused
   - Verify tab order: textarea → More → Send/Cancel → Clear

### Property-Based Testing Approach

Property-based tests will verify universal behaviors across many generated inputs. Tests will use fast-check library with minimum 100 iterations per test.

**Property Test Configuration:**
- Library: fast-check (JavaScript/TypeScript property-based testing)
- Iterations: 100 minimum per property
- Tagging: Each test references its design document property

**Property Tests:**

1. **Property 1: Button Enablement Preconditions**
   - Generate random combinations of (connected, selectedDocuments, topicName, thinking)
   - Verify button enabled state matches: connected && hasDocuments && hasTopic && !thinking
   - Tag: **Feature: explorer-more-button, Property 1: Button enablement preconditions**

2. **Property 2: Message Transmission**
   - Generate random valid states (enabled button conditions)
   - Generate random topic names and document ID sets
   - Simulate button click
   - Verify wsSend called with correct message structure
   - Tag: **Feature: explorer-more-button, Property 2: Message transmission**

3. **Property 3: Textarea Clearing**
   - Generate random textarea content (empty, whitespace, text)
   - Simulate More button click
   - Verify textarea is empty after click
   - Tag: **Feature: explorer-more-button, Property 3: Textarea clearing**

4. **Property 4: Thinking State Activation**
   - Generate random valid component states
   - Simulate More button click
   - Verify thinking state is true after click
   - Tag: **Feature: explorer-more-button, Property 4: Thinking state activation**

5. **Property 5: Pending Question Display**
   - Generate random valid component states
   - Simulate More button click
   - Verify pendingQuestion equals DEEPER_ANALYSIS_PROMPT
   - Tag: **Feature: explorer-more-button, Property 5: Pending question display**

6. **Property 6: Keyboard Activation**
   - Generate random valid component states
   - Generate random key events (Enter, Space, other keys)
   - Simulate key press on focused More button
   - Verify handleMore is called only for Enter and Space keys
   - Tag: **Feature: explorer-more-button, Property 6: Keyboard activation**

### Test File Organization

```
tests/experimental/shared/frontend/
└── ChatArea.test.tsx
    ├── Unit Tests
    │   ├── Rendering
    │   ├── State-Based Enablement
    │   ├── Click Behavior
    │   ├── Integration
    │   ├── Constants
    │   └── Accessibility
    └── Property Tests
        ├── Property 1: Button Enablement
        ├── Property 2: Message Transmission
        ├── Property 3: Textarea Clearing
        ├── Property 4: Thinking State
        ├── Property 5: Pending Question
        └── Property 6: Keyboard Activation
```

### Testing Balance

- **Unit tests** verify specific examples, edge cases, and integration points
- **Property tests** verify universal behaviors across all valid inputs
- Together they provide comprehensive coverage: unit tests catch concrete bugs, property tests verify general correctness

The dual approach ensures both specific scenarios (e.g., "button disabled when connected=false") and general rules (e.g., "button enabled if and only if all preconditions met") are validated.

