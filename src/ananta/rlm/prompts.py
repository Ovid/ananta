"""Hardened system prompts for RLM execution."""

# Maximum characters per sub-LLM call (used for guidance in prompt)
MAX_SUBCALL_CHARS = 500_000


def truncate_code_output(output: str, max_chars: int = 20_000) -> str:
    """Truncate a single code block's output to max_chars.

    This matches the reference RLM's 20K per-block limit
    (rlm/rlm/utils/parsing.py:67). The limit is a forcing function:
    when the model can't see full output, it must use llm_query()
    to analyze content it cannot see.
    """
    if len(output) <= max_chars:
        return output
    return (
        output[:max_chars] + f"\n[Output truncated to {max_chars:,} of {len(output):,} characters. "
        f"Use llm_query() to analyze content you cannot see.]"
    )


def format_code_echo(
    code: str,
    output: str,
    vars: dict[str, str] | None = None,
    boundary: str | None = None,
) -> str:
    """Format a code block and its output as a code echo message.

    Matches the reference RLM's per-block feedback format
    (rlm/rlm/utils/parsing.py:93-96).

    When ``boundary`` is provided, the REPL output is wrapped in
    randomized untrusted content markers.
    """
    from shesha.rlm.boundary import wrap_untrusted  # Local import to avoid circular dependency

    if boundary is not None:
        output = wrap_untrusted(output, boundary)
    parts = [f"Code executed:\n```python\n{code}\n```\n\nREPL output:\n{output}"]
    if vars:
        parts.append(f"\nREPL variables: {list(vars.keys())}")
    return "\n".join(parts)
