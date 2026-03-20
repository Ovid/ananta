# Ananta Prompts

This directory contains the LLM prompt templates used by Ananta. You can customize these prompts to tune behavior for your use case.

## Prompt Files

| File | Purpose |
|------|---------|
| `system.md` | Main system prompt for the RLM core loop. Defines available functions, working patterns, chunking strategies, and security warnings. |
| `subcall.md` | Template for sub-LLM calls when analyzing document chunks. Wraps content in security tags. |
| `code_required.md` | Follow-up message when LLM response doesn't contain code. |

## Placeholders

Prompts use `{placeholder}` syntax. Available placeholders per file:

### system.md

| Placeholder | Description |
|-------------|-------------|
| `{doc_count}` | Number of documents loaded |
| `{total_chars}` | Total characters across all documents |
| `{doc_sizes_list}` | Formatted list of document names and sizes |
| `{max_subcall_chars}` | Character limit for sub-LLM calls (500,000) |

Use `{name:,}` for comma-formatted numbers (e.g., `{total_chars:,}` renders as "10,000").

### subcall.md

| Placeholder | Description |
|-------------|-------------|
| `{instruction}` | The analysis instruction (trusted) |
| `{content}` | Document content being analyzed (untrusted) |

### code_required.md

No placeholders. Static message.

## Creating Custom Prompt Sets

1. Copy the entire `prompts/` directory:
   ```bash
   cp -r prompts/ my-prompts/
   ```

2. Edit the files in `my-prompts/`

3. Validate your changes:
   ```bash
   python -m ananta.prompts --prompts-dir ./my-prompts
   ```

4. Use your custom prompts:
   ```bash
   export ANANTA_PROMPTS_DIR=./my-prompts
   # or
   ananta query --prompts-dir ./my-prompts ...
   ```

## Validation

After editing prompts, validate them:

```bash
python -m ananta.prompts --prompts-dir ./prompts
```

The validator checks:
- All required files exist
- All required placeholders are present
- No unknown placeholders (catches typos)

## Environment Variable

Set `ANANTA_PROMPTS_DIR` to use a custom prompts directory by default:

```bash
export ANANTA_PROMPTS_DIR=/path/to/my-prompts
```

CLI `--prompts-dir` overrides the environment variable when specified.
