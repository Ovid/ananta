# PRD-HLD Alignment Verification

Verify that the HLD completely addresses the PRD without scope creep.

## PRD

{prd}

## HLD

{hld}

## Your Task

1. **Coverage Check** - For each requirement in the PRD, identify which HLD section addresses it. Flag any requirements with no coverage.

2. **Scope Check** - For each change in the HLD, trace it back to a PRD requirement. Flag any changes not justified by the PRD.

3. **Recommendation** - Based on coverage and scope:
   - "approved" - HLD fully covers PRD with no scope creep
   - "revise" - Minor gaps or scope creep that can be fixed
   - "major_gaps" - Significant requirements missing

## Output Format

```json
{
  "covered": [
    {"requirement": "PRD requirement text", "hld_section": "HLD section that addresses it"}
  ],
  "gaps": [
    {"requirement": "PRD requirement text", "reason": "why it's not covered"}
  ],
  "scope_creep": [
    {"hld_item": "HLD item", "reason": "why it's not justified by PRD"}
  ],
  "alignment_score": 0.0-1.0,
  "recommendation": "approved|revise|major_gaps"
}
```

After the JSON, provide reasoning for your assessment.
