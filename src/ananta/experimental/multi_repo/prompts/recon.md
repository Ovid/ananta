# Repository Reconnaissance

Analyze this codebase to identify its structure and interfaces.

## Your Task

Extract the following information:

1. **Public APIs** - REST endpoints, GraphQL queries/mutations, gRPC services, exported functions, CLI commands
2. **Data Models** - Database schemas, DTOs, domain objects, message formats
3. **Entry Points** - Main files, request handlers, event listeners, CLI entrypoints
4. **External Dependencies** - Other services this code calls, external APIs, message queues

## Output Format

Respond with a structured summary. Focus on INTERFACES - what this system exposes and what it consumes. Skip internal implementation details.

```json
{
  "apis": ["list of public API endpoints/functions"],
  "models": ["list of data structures"],
  "entry_points": ["list of main entry points"],
  "dependencies": ["list of external services called"]
}
```

After the JSON, provide a brief narrative summary explaining the system's role.
