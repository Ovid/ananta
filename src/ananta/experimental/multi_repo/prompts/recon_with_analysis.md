# Repository Reconnaissance (with existing analysis)

An existing codebase analysis has been provided below. Use it as a guide to understand the repository structure, but verify and supplement it by exploring the actual code.

## Existing Analysis

{existing_analysis}

## Your Task

Using the existing analysis as context:

1. **Verify** the analysis is accurate by checking the actual code
2. **Supplement** with any APIs, models, or entry points the analysis missed
3. **Update** any information that appears outdated or incorrect

Focus on extracting:
- Public APIs (REST endpoints, GraphQL operations, gRPC services, CLI commands)
- Data models and schemas
- Entry points and handlers
- External dependencies

## Output Format

Return a JSON object:

```json
{
  "apis": ["GET /api/users", "POST /api/auth/login"],
  "models": ["User", "Session", "AuthToken"],
  "entry_points": ["src/main.py", "src/api/routes.py"],
  "dependencies": ["PostgreSQL", "Redis", "auth-service"]
}
```

Note: The `dependencies` field should list both external services AND internal dependencies on other repositories/services that this codebase interacts with.
