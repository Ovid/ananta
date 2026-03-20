# HLD Synthesis

Create a High-Level Design document from the PRD and impact analyses.

## PRD

{prd}

## Impact Reports

{impact_reports}

## Your Task

Create a comprehensive High-Level Design covering:

1. **Component Changes** - For each system, what needs to change
2. **Data Flow** - How data moves between systems for this feature (include a diagram if helpful)
3. **Interface Contracts** - API specifications, event schemas, message formats
4. **Implementation Sequence** - What order to build/deploy changes (consider dependencies)
5. **Open Questions** - Ambiguities that need human decision

## Output Format

First, provide structured data:

```json
{
  "component_changes": {
    "repo-name": ["list of changes"]
  },
  "data_flow": "description or mermaid diagram",
  "interface_contracts": ["list of API/event specs"],
  "implementation_sequence": ["ordered list of steps"],
  "open_questions": ["list of decisions needed"]
}
```

Then provide the full HLD as markdown, suitable for engineering review.
