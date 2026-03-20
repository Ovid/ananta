# Codebase Analysis

Analyze this codebase and produce a structured analysis in JSON format. Your goal is to identify the major components, their public APIs, data models, entry points, and external dependencies.

## Instructions

1. Explore the codebase structure to understand the major components/services
2. For each component, identify:
   - Public APIs (REST endpoints, GraphQL operations, gRPC services, CLI commands, event handlers)
   - Key data models and schemas
   - Main entry points (startup files, handlers)
   - Dependencies on other components in the same codebase
   - Authentication mechanisms (if any)
   - Data persistence mechanisms (if any)
3. Identify external dependencies (third-party services, databases, message queues)
4. Write a high-level overview summarizing what this codebase does

## Output Format

Return a JSON object with this structure:

```json
{
  "overview": "A 2-3 sentence summary of what this codebase does and its primary purpose.",
  "components": [
    {
      "name": "Component Name",
      "path": "path/to/component/",
      "description": "What this component does",
      "apis": [
        {
          "type": "rest",
          "endpoints": ["GET /api/users", "POST /api/users"]
        }
      ],
      "models": ["User", "Session"],
      "entry_points": ["path/to/main.py"],
      "internal_dependencies": ["other-component-name"],
      "auth": "Description of auth mechanism or null",
      "data_persistence": "Description of storage or null"
    }
  ],
  "external_dependencies": [
    {
      "name": "Service Name",
      "type": "database|external_api|message_queue|ai_service|auth_service|storage",
      "description": "How this dependency is used",
      "used_by": ["component-name"],
      "optional": false
    }
  ]
}
```

## API Types

Use these types for the `apis` array:
- `rest`: REST API endpoints
- `graphql`: GraphQL queries/mutations
- `grpc`: gRPC service methods
- `cli`: Command-line interface commands
- `events`: Event handlers or message consumers

## Important Notes

- Focus on PUBLIC interfaces that other systems might integrate with
- Include internal component dependencies to show how the system is structured
- Mark external dependencies as `optional: true` if the system can function without them
- Be specific about endpoints and models - list actual names, not placeholders
