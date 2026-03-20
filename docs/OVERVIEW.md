# Overview Guide

## How Ananta Works

Ananta implements Recursive Language Models (RLMs). The core idea: instead of feeding documents directly to an LLM, give the LLM a Python REPL and let it write code to explore the documents iteratively.

**The Query Loop** (`rlm/engine.py`):

1. User asks a question
2. Documents are loaded into a sandboxed Python environment as `context` (a dict)
3. LLM receives the question + a system prompt explaining the REPL
4. LLM writes Python code in a ` ```repl ` block
5. Code executes in Docker sandbox, output returns to LLM
6. LLM sees output, writes more code (or calls `FINAL("answer")` to finish)
7. Loop continues until `FINAL()` or max iterations

**Sub-LLM Calls**: For large documents, the sandbox provides `llm_query(instruction, content)`. This delegates analysis to a sub-LLM call - useful for summarizing chunks too large to reason about directly.

**Security Model**: All document content is untrusted. The sandbox is network-isolated. Sub-LLM content is wrapped in `<untrusted_document_content>` tags to prevent prompt injection.

## Code Organization

```
src/ananta/
├── ananta.py          # Main entry point - creates projects, manages lifecycle
├── project.py         # Project class - upload docs, run queries
├── config.py          # AnantaConfig - loads from env/file/args
├── models.py          # Data classes (ParsedDocument, RepoProjectResult, etc.)
├── exceptions.py      # Exception hierarchy
│
├── rlm/               # The RLM engine (core loop)
│   ├── engine.py      # RLMEngine.query() - the REPL+LLM loop
│   ├── prompts.py     # System prompts, output wrapping, security tags
│   └── trace.py       # Execution tracing (steps, tokens, timing)
│
├── sandbox/           # Docker-based code execution
│   ├── pool.py        # ContainerPool - keeps warm containers ready
│   ├── executor.py    # ContainerExecutor - runs code, handles llm_query
│   ├── runner.py      # Runs INSIDE the container (receives JSON commands)
│   └── Dockerfile     # The sandbox image
│
├── parser/            # Document parsing
│   ├── base.py        # DocumentParser protocol
│   ├── registry.py    # ParserRegistry - finds parser by file type
│   ├── code.py        # Source code (with line numbers, shebang detection)
│   ├── text.py        # Plain text, markdown, CSV
│   ├── pdf.py         # PDF extraction
│   ├── office.py      # Word documents
│   └── html.py        # HTML to text
│
├── storage/           # Document persistence
│   ├── base.py        # StorageBackend protocol
│   └── filesystem.py  # FilesystemStorage implementation
│
├── repo/              # Git repository ingestion
│   └── ingester.py    # Clone, pull, list files, track SHA
│
└── llm/               # LLM client
    └── client.py      # LLMClient - wraps LiteLLM
```

## Where to Look

**"I want to change how queries work"**
→ `rlm/engine.py` - the main loop is `RLMEngine.query()`

**"I want to change what the LLM sees"**
→ `rlm/prompts.py` - system prompts, REPL output wrapping, security tags

**"I want to add a new document type"**
→ `parser/` - create a new parser implementing `DocumentParser` protocol, register in `parser/__init__.py`

**"I want to change how code runs in the sandbox"**
→ `sandbox/runner.py` (inside container) or `sandbox/executor.py` (host side)

**"I want to change container management"**
→ `sandbox/pool.py` - warm container pool, lifecycle

**"I want to change how documents are stored"**
→ `storage/filesystem.py` or create a new `StorageBackend` implementation

**"I want to change git repo handling"**
→ `repo/ingester.py` - clone, pull, SHA tracking, file listing

**"I want to change the public API"**
→ `ananta.py` (top-level) or `project.py` (project operations)

**"I want to change configuration options"**
→ `config.py` - `AnantaConfig` dataclass, env var loading

**"I want to add a new LLM provider"**
→ You probably don't need to - LiteLLM handles this. Check `llm/client.py` if you need custom behavior.
