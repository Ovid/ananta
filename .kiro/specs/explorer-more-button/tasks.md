# Implementation Plan: Explorer More Button

## Overview

This plan implements a "More" button in the shared ChatArea component that enables users to request deeper analysis with a single click. The implementation follows strict red/green/refactor methodology with clear cycles.

The feature uses TypeScript/React and integrates with the existing WebSocket-based message flow. Property-based tests will use fast-check with minimum 100 iterations per property.

## Red/Green/Refactor Cycles

### Cycle 0: Test Infrastructure Setup

- [x] 0.1 RED: Set up test infrastructure
  - Create test file at `src/shesha/experimental/shared/frontend/src/components/__tests__/ChatArea.test.tsx`
  - Import React Testing Library, Vitest, and fast-check
  - Define DEEPER_ANALYSIS_PROMPT constant matching requirements
  - Set up mock WebSocket send function and component props
  - Create helper function to render ChatArea with default props
  - _Requirements: 3.2, 4.1_
  - _Verification: Test file exists and imports are valid_

---

### Cycle 1: More Button Rendering

- [x] 1.1 RED: Write failing tests for button rendering
  - Test: More button exists with text "More"
  - Test: More button is positioned between textarea and Send button
  - Test: More button is hidden when thinking=true
  - Run tests → verify they fail
  - _Requirements: 1.1, 1.2, 1.4, 2.3_

- [x] 1.2 GREEN: Implement More button UI
  - Add DEEPER_ANALYSIS_PROMPT constant to ChatArea.tsx
  - Add More button JSX between textarea and Send button
  - Add conditional rendering: `{!thinking && <button>More</button>}`
  - Apply Tailwind styling consistent with other buttons
  - Run tests → verify they pass
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 3.2_

- [x] 1.3 REFACTOR: Clean up if needed
  - Review button styling for consistency
  - Ensure proper spacing and layout
  - Run tests → verify still passing

---

### Cycle 2: Button Enablement Logic

- [x] 2.1 RED: Write failing tests for button enablement
  - Test: Button disabled when connected=false
  - Test: Button disabled when selectedDocuments=undefined
  - Test: Button disabled when selectedDocuments is empty Set
  - Test: Button disabled when topicName=null
  - Test: Button enabled when all conditions met
  - Run tests → verify they fail
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 2.2 GREEN: Implement enablement logic
  - Add canSendMore computed value: `!!topicName && !thinking && connected && hasDocuments`
  - Add disabled attribute to More button: `disabled={!canSendMore}`
  - Run tests → verify they pass
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 2.3 REFACTOR: Clean up if needed
  - Extract hasDocuments logic if not already present
  - Add inline comment explaining canSendMore logic
  - Run tests → verify still passing

---

### Cycle 3: Click Behavior

- [x] 3.1 RED: Write failing tests for click behavior
  - Test: Clicking More calls wsSend with correct message structure
  - Test: Clicking More clears textarea content
  - Test: Clicking More sets thinking=true
  - Test: Clicking More sets pendingQuestion to DEEPER_ANALYSIS_PROMPT
  - Test: Clicking More sets pendingSentAt timestamp
  - Run tests → verify they fail
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 4.3_

- [x] 3.2 GREEN: Implement click handler
  - Add handleMore callback using useCallback
  - Implement: wsSend call, setInput(''), setPendingQuestion, setPendingSentAt, setThinking(true), setPhase('Starting')
  - Add onClick={handleMore} to More button
  - Run tests → verify they pass
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 4.3_

- [x] 3.3 REFACTOR: Extract common logic
  - Check if handleMore and handleSend share logic
  - Extract shared message building if applicable
  - Add JSDoc comment for handleMore
  - Run tests → verify still passing

---

### Cycle 4: Accessibility Features

- [x] 4.1 RED: Write failing tests for accessibility
  - Test: More button has correct tab order (textarea → More → Send → Clear)
  - Test: More button has visible focus indicator
  - Test: More button has aria-label="Request deeper analysis"
  - Test: More button has aria-disabled matching disabled state
  - Test: Enter key activates More button when focused
  - Test: Space key activates More button when focused
  - Run tests → verify they fail
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 4.2 GREEN: Implement accessibility features
  - Add aria-label="Request deeper analysis"
  - Add aria-disabled={!canSendMore}
  - Add focus styles: `focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2`
  - Add onKeyDown handler for Enter and Space keys
  - Run tests → verify they pass
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 4.3 REFACTOR: Clean up accessibility code
  - Ensure keyboard handler uses preventDefault correctly
  - Verify focus styles are consistent with design system
  - Run tests → verify still passing

---

### Cycle 5: Integration Testing

- [x] 5.1 RED: Write failing integration tests
  - Test: More button appears in arXiv explorer
  - Test: More button appears in code explorer
  - Test: More button appears in document explorer
  - Run tests → verify they fail
  - _Requirements: 4.2_

- [x] 5.2 GREEN: Verify integration
  - No code changes needed (shared component pattern)
  - Run tests → verify they pass
  - _Requirements: 4.1, 4.2_

- [x] 5.3 REFACTOR: Not applicable for integration tests

---

### Cycle 6: User Experience Consistency

- [x] 6.1 RED: Write failing UX consistency tests
  - Test: More button click displays thinking indicator
  - Test: More button click displays phase updates
  - Test: Cancel button available during More request
  - Test: History reloads on More request completion
  - Test: Error toast displayed on More request failure
  - Run tests → verify they fail
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 6.2 GREEN: Verify UX consistency
  - No code changes needed (inherited from shared infrastructure)
  - Run tests → verify they pass
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 6.3 REFACTOR: Not applicable for inherited behavior

---

### Checkpoint: All Unit and Integration Tests Passing

- [x] 7.0 Run full test suite
  - Execute all tests written so far
  - Verify no failures or warnings
  - If any issues, fix before proceeding
  - _Verification: All tests green_

---

### Cycle 7: Property-Based Test - Button Enablement

- [x] 7.1 RED: Write property test for button enablement
  - **Property 1: Button Enablement Preconditions**
  - Generate random combinations of (connected, selectedDocuments, topicName, thinking)
  - Verify button enabled iff: connected && hasDocuments && hasTopic && !thinking
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 1"
  - Run test → verify it fails
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 7.2 GREEN: Verify property test passes
  - No code changes needed (logic already implemented)
  - Run test → verify it passes
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 7.3 REFACTOR: Not applicable

---

### Cycle 8: Property-Based Test - Message Transmission (OPTIONAL)

- [x] 8.1 RED: Write property test for message transmission
  - **Property 2: Message Transmission**
  - Generate random valid states and document sets
  - Simulate button click
  - Verify wsSend called with correct structure
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 2"
  - Run test → verify it fails
  - _Requirements: 3.1, 4.3_

- [x] 8.2 GREEN: Verify property test passes
  - No code changes needed
  - Run test → verify it passes
  - _Requirements: 3.1, 4.3_

- [x] 8.3 REFACTOR: Not applicable

---

### Cycle 9: Property-Based Test - Textarea Clearing (OPTIONAL)

- [x] 9.1 RED: Write property test for textarea clearing
  - **Property 3: Textarea Clearing**
  - Generate random textarea content
  - Simulate More button click
  - Verify textarea is empty after click
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 3"
  - Run test → verify it fails
  - _Requirements: 3.3_

- [x] 9.2 GREEN: Verify property test passes
  - No code changes needed
  - Run test → verify it passes
  - _Requirements: 3.3_

- [x] 9.3 REFACTOR: Not applicable

---

### Cycle 10: Property-Based Test - Thinking State (OPTIONAL)

- [x] 10.1 RED: Write property test for thinking state
  - **Property 4: Thinking State Activation**
  - Generate random valid component states
  - Simulate More button click
  - Verify thinking state is true after click
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 4"
  - Run test → verify it fails
  - _Requirements: 3.4_

- [x] 10.2 GREEN: Verify property test passes
  - No code changes needed
  - Run test → verify it passes
  - _Requirements: 3.4_

- [x] 10.3 REFACTOR: Not applicable

---

### Cycle 11: Property-Based Test - Pending Question (OPTIONAL)

- [x] 11.1 RED: Write property test for pending question
  - **Property 5: Pending Question Display**
  - Generate random valid component states
  - Simulate More button click
  - Verify pendingQuestion equals DEEPER_ANALYSIS_PROMPT
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 5"
  - Run test → verify it fails
  - _Requirements: 3.5_

- [x] 11.2 GREEN: Verify property test passes
  - No code changes needed
  - Run test → verify it passes
  - _Requirements: 3.5_

- [x] 11.3 REFACTOR: Not applicable

---

### Cycle 12: Property-Based Test - Keyboard Activation (OPTIONAL)

- [x] 12.1 RED: Write property test for keyboard activation
  - **Property 6: Keyboard Activation**
  - Generate random valid states and key events
  - Simulate key press on focused More button
  - Verify handleMore called only for Enter and Space
  - Use fast-check with minimum 100 iterations
  - Tag: "Feature: explorer-more-button, Property 6"
  - Run test → verify it fails
  - _Requirements: 6.3_

- [x] 12.2 GREEN: Verify property test passes
  - No code changes needed
  - Run test → verify it passes
  - _Requirements: 6.3_

- [x] 12.3 REFACTOR: Not applicable

---

### Final Refactor Cycle

- [ ] 13.1 REFACTOR: Code quality review
  - Review all code for duplication
  - Ensure consistent formatting (run linter/formatter)
  - Add/update code comments for clarity
  - Document DEEPER_ANALYSIS_PROMPT constant
  - Document canSendMore logic
  - _Requirements: 1.3, 3.2, 2.5, 4.3_

- [ ] 13.2 REFACTOR: Run full test suite
  - Execute all tests including property tests
  - Verify no regressions
  - Verify no warnings or errors
  - _Requirements: All_

---

## Implementation Notes

- Tasks marked with `*` are optional property-based tests
- Each cycle follows strict RED → GREEN → REFACTOR order
- Never write implementation code before tests fail
- Never move to next cycle until current tests pass
- Refactor steps are optional if code is already clean
- Property tests verify implementation, not drive it (tests written after GREEN phase)
- Integration and UX consistency tests verify inherited behavior
- At the end of each task, **commit your changes**

## Success Criteria

- All unit tests pass
- All integration tests pass
- All accessibility tests pass
- All property-based tests pass
- No console warnings or errors
- Code is clean, documented, and follows project conventions
