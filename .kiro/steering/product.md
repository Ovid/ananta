---
inclusion: always
---

# Product: Ananta

Ananta is a Python library for querying large document collections using Recursive Language Models (RLMs), based on arXiv:2512.24601. Instead of RAG-style snippet retrieval, the LLM writes and executes Python code in a sandboxed Docker container to actively explore documents, iterating until it finds a confident answer with citations.

Core flow: User Query → RLM Engine → LLM generates Python code → Docker sandbox executes it → LLM sees output → repeats until `FINAL("answer")`.

Key capabilities:
- Query text, PDF, DOCX, HTML, and code files across project-scoped document collections
- Ingest and analyze entire git repositories (GitHub, GitLab, Bitbucket, local)
- Sub-LLM delegation via `llm_query(instruction, content)` for large documents
- Execution tracing for transparency
- Security-hardened: network-isolated containers, untrusted content tagging, prompt injection defenses
- 100+ LLM providers via LiteLLM (OpenAI, Anthropic, Google, Ollama, etc.)

Experimental features: arXiv paper explorer (web UI), code explorer, document explorer, multi-repo analysis. All explorers share a common framework (app factory, shared routes, websocket infrastructure).
