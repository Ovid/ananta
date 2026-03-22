# Requirements Document

## Introduction

This feature adds a "More" button to the chat interface of all three Ananta explorers (arXiv explorer, code explorer, and document explorer). The button enables users to request a deeper analysis with a single click, automatically sending a predefined prompt that asks the system to verify and enhance its previous response.

## Glossary

- **ChatArea**: The shared React component that handles the prompt input and message sending functionality across all three explorers
- **Explorer**: One of the three Ananta web interfaces (arXiv explorer, code explorer, or document explorer)
- **More_Button**: The new UI button that triggers the deeper analysis prompt
- **Deeper_Analysis_Prompt**: The predefined text "Do a deeper dive to verify if your report is complete, accurate, and relevant. Explain any changes or additions in bullet points and then present the full report with those changes and/or additions. You must also walk through the entire report, point by point, and ensure its aligned with the previous report and the changes or additions."
- **Send_Flow**: The existing message sending mechanism that transmits user queries via WebSocket

## Requirements

### Requirement 1: More Button UI Component

**User Story:** As a user, I want to see a "More" button next to the prompt input area, so that I can easily request deeper analysis without typing.

#### Acceptance Criteria

1. THE More_Button SHALL be positioned to the right of the prompt textarea and to the left of the Send button
2. THE More_Button SHALL display the text "More"
3. THE More_Button SHALL use consistent styling with other buttons in the ChatArea component
4. THE More_Button SHALL be visible at all times when the ChatArea is rendered

### Requirement 2: Button State Management

**User Story:** As a user, I want the More button to be enabled only when appropriate, so that I don't accidentally trigger analysis when the system isn't ready.

#### Acceptance Criteria

1. WHEN the WebSocket is not connected, THE More_Button SHALL be disabled
2. WHEN no documents are selected, THE More_Button SHALL be disabled
3. WHEN the system is currently thinking, THE More_Button SHALL be disabled
4. WHEN no topic is selected, THE More_Button SHALL be disabled
5. WHEN all conditions are met (connected, has documents, has topic, not thinking), THE More_Button SHALL be enabled

### Requirement 3: Deeper Analysis Prompt Submission

**User Story:** As a user, I want the More button to automatically send a deeper analysis request, so that I can get enhanced results with one click.

#### Acceptance Criteria

1. WHEN the More_Button is clicked, THE ChatArea SHALL send the Deeper_Analysis_Prompt through the existing Send_Flow
2. THE Deeper_Analysis_Prompt SHALL be "Do a deeper dive to verify if your report is complete, accurate, and relevant. Explain any changes or additions in bullet points and then present the full report with those changes and/or additions. You must also walk through the entire report, point by point, and ensure its aligned with the previous report and the changes or additions."
3. WHEN the More_Button is clicked, THE ChatArea SHALL clear any existing text in the prompt textarea
4. WHEN the More_Button is clicked, THE ChatArea SHALL set the thinking state to true
5. WHEN the More_Button is clicked, THE ChatArea SHALL display the Deeper_Analysis_Prompt as a pending question in the chat history

### Requirement 4: Shared Component Implementation

**User Story:** As a developer, I want the More button implemented in the shared ChatArea component, so that all three explorers automatically inherit the functionality.

#### Acceptance Criteria

1. THE More_Button SHALL be implemented in the shared ChatArea component located at src/ananta/explorers/shared_ui/frontend/src/components/ChatArea.tsx
2. WHEN any explorer uses the ChatArea component, THE More_Button SHALL be available without additional configuration
3. THE More_Button SHALL use the same WebSocket send mechanism (wsSend) as the existing Send button
4. THE More_Button SHALL respect the same document selection constraints (selectedDocuments) as the existing Send button

### Requirement 5: User Experience Consistency

**User Story:** As a user, I want the More button to behave like the Send button, so that the interaction feels natural and consistent.

#### Acceptance Criteria

1. WHEN the More_Button is clicked, THE ChatArea SHALL display the same visual feedback (thinking indicator, phase updates) as when the Send button is clicked
2. WHEN the system is processing a More_Button request, THE Cancel button SHALL be available to stop the analysis
3. WHEN the More_Button request completes, THE ChatArea SHALL reload the conversation history to display the new exchange
4. WHEN the More_Button request encounters an error, THE ChatArea SHALL display an error toast message

### Requirement 6: Accessibility

**User Story:** As a user with accessibility needs, I want the More button to be fully accessible via keyboard and screen readers, so that I can use the feature regardless of my input method or assistive technology.

#### Acceptance Criteria

1. THE More_Button SHALL be reachable via keyboard Tab navigation in the correct order (textarea → More button → Send/Cancel button → Clear button)
2. THE More_Button SHALL display a visible focus indicator when focused via keyboard navigation
3. THE More_Button SHALL be activatable via both Enter and Space keys when focused
4. THE More_Button SHALL have an aria-label attribute with the value "Request deeper analysis" for screen reader users
5. THE More_Button SHALL have an aria-disabled attribute that reflects the button's enabled/disabled state
6. THE More_Button focus indicator SHALL use a high-contrast ring with sufficient offset to ensure visibility
