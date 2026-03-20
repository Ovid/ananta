# PRD Impact Analysis

Analyze how this PRD affects the given repository.

## PRD

{prd}

## Repository Summary

{repo_summary}

## Your Task

Determine:

1. **Affected?** - Does this PRD require changes to this codebase? (yes/no with reasoning)
2. **Changes Needed** - What specific changes are required? Be concrete: new endpoints, modified models, updated handlers.
3. **New Interfaces** - What new APIs, events, or schemas need to be created?
4. **Modified Interfaces** - What existing interfaces need to change?
5. **Discovered Dependencies** - What other systems might this repo need to interact with that aren't mentioned in the analysis so far?

## Output Format

```json
{
  "affected": true/false,
  "changes": ["list of specific changes needed"],
  "new_interfaces": ["list of new APIs/events to create"],
  "modified_interfaces": ["list of existing APIs to modify"],
  "discovered_dependencies": ["list of other systems that may need analysis"]
}
```

After the JSON, provide reasoning for your assessment.
