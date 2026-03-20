"""Tests for RLM prompts."""

from ananta.prompts import PromptLoader
from ananta.rlm.prompts import truncate_code_output


def test_system_prompt_no_longer_contains_metadata():
    """System prompt does not contain dynamic metadata placeholders."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "{doc_count}" not in prompt
    assert "{total_chars" not in prompt
    assert "{doc_sizes_list}" not in prompt


def test_system_prompt_explains_final():
    """System prompt explains FINAL function."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "FINAL" in prompt


def test_subcall_prompt_contains_content():
    """Subcall prompt contains instruction and content."""
    loader = PromptLoader()

    prompt = loader.render_subcall_prompt(
        instruction="Summarize this",
        content="Document content here",
    )
    assert "Document content here" in prompt
    assert "Summarize this" in prompt


def test_system_prompt_contains_sub_llm_limit():
    """System prompt tells LLM about sub-LLM character limit."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "500K" in prompt or "500,000" in prompt or "500000" in prompt


def test_system_prompt_contains_chunking_guidance():
    """System prompt explains chunking strategy for large documents."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    prompt_lower = prompt.lower()
    assert "chunk" in prompt_lower


def test_subcall_prompt_no_size_limit():
    """Subcall prompt passes content through without modification."""
    loader = PromptLoader()
    large_content = "x" * 600_000  # 600K chars

    prompt = loader.render_subcall_prompt(
        instruction="Summarize this",
        content=large_content,
    )

    # Content should be passed through completely
    assert large_content in prompt


def test_context_metadata_prompt_exists():
    """PromptLoader can render context metadata."""
    loader = PromptLoader()
    result = loader.render_context_metadata(
        context_type="list",
        context_total_length=15000,
        context_lengths="[5000, 4000, 6000]",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_context_metadata_contains_doc_info():
    """Rendered context metadata includes type, total chars, and chunk lengths."""
    loader = PromptLoader()
    result = loader.render_context_metadata(
        context_type="list",
        context_total_length=15000,
        context_lengths="[5000, 4000, 6000]",
    )
    assert "list" in result
    assert "15000" in result
    assert "[5000, 4000, 6000]" in result


def test_code_required_prompt():
    """code_required prompt asks for REPL code."""
    loader = PromptLoader()

    prompt = loader.render_code_required()

    # Should ask for code in a repl block
    assert "repl" in prompt.lower() or "code" in prompt.lower()


def test_truncate_code_output_under_limit():
    """Output under the limit is returned unchanged."""
    output = "x" * 19000  # Under 20K

    result = truncate_code_output(output, max_chars=20_000)

    assert result == output


def test_truncate_code_output_over_limit():
    """Output over the limit is truncated with a nudge message."""
    output = "x" * 25000  # Over 20K

    result = truncate_code_output(output, max_chars=20_000)

    # Should be truncated to max_chars
    assert len(result) < len(output)
    # Should include nudge message referencing llm_query()
    assert "truncated" in result.lower()
    assert "20,000" in result
    assert "25,000" in result
    assert "llm_query()" in result


def test_truncate_code_output_exact_limit():
    """Output exactly at the limit is returned unchanged."""
    output = "x" * 20_000

    result = truncate_code_output(output, max_chars=20_000)

    assert result == output


def test_iteration_zero_prompt_exists():
    """PromptLoader can render an iteration-0 prompt template."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_iteration_zero_prompt_contains_safeguard():
    """Rendered iteration-0 template includes safeguard language."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "don't just provide a final answer yet" in result.lower()
    assert "look through" in result.lower()


def test_iteration_zero_prompt_includes_question():
    """Rendered iteration-0 template includes the question."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "What color is the sky?" in result


def test_system_prompt_encourages_subcall_use():
    """System prompt encourages using llm_query for semantic analysis."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    prompt_lower = prompt.lower()
    assert "strongly encouraged" in prompt_lower
    assert "batch" in prompt_lower or "batched" in prompt_lower


def test_system_prompt_truncation_warning():
    """System prompt warns that REPL output is truncated to motivate sub-call usage."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    prompt_lower = prompt.lower()
    assert "truncated" in prompt_lower


def test_system_prompt_confidence_framing():
    """System prompt encourages heavy sub-call usage with confidence framing."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    prompt_lower = prompt.lower()
    assert "powerful" in prompt_lower
    assert "don't be afraid" in prompt_lower


def test_system_prompt_examples_use_llm_query():
    """Examples demonstrate llm_query or llm_query_batched usage."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "llm_query(" in prompt
    assert "llm_query_batched(" in prompt


def test_iteration_continue_prompt_exists():
    """PromptLoader can render an iteration-continue prompt template."""
    loader = PromptLoader()
    result = loader.render_iteration_continue(question="What color is the sky?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_iteration_continue_prompt_mentions_sub_llms():
    """Rendered iteration-continue template mentions sub-LLMs."""
    loader = PromptLoader()
    result = loader.render_iteration_continue(question="What color is the sky?")
    assert "sub-LLM" in result or "sub-llm" in result.lower() or "querying" in result.lower()


def test_format_code_echo_message():
    """Code echo message contains both the code and output."""
    from ananta.rlm.prompts import format_code_echo

    code = 'print("hello")'
    output = "hello"
    result = format_code_echo(code, output)

    assert "Code executed:" in result
    assert 'print("hello")' in result
    assert "```python" in result
    assert "REPL output:" in result
    assert "hello" in result


def test_format_code_echo_with_vars():
    """Code echo includes REPL variables list when vars provided."""
    from ananta.rlm.prompts import format_code_echo

    code = "x = 42"
    output = ""
    vars_dict = {"x": "int", "answer": "str"}
    result = format_code_echo(code, output, vars=vars_dict)

    assert "REPL variables:" in result
    assert "x" in result
    assert "answer" in result


def test_format_code_echo_without_vars():
    """Code echo omits REPL variables when vars is None."""
    from ananta.rlm.prompts import format_code_echo

    code = 'print("hello")'
    output = "hello"
    result = format_code_echo(code, output)

    assert "REPL variables:" not in result
    assert "REPL output:" in result
    assert "hello" in result


def test_format_code_echo_no_repl_output_tags():
    """Code echo uses plain 'REPL output:' not XML tags."""
    from ananta.rlm.prompts import format_code_echo

    result = format_code_echo("code", "output")
    assert "<repl_output" not in result
    assert "REPL output:" in result


def test_system_prompt_describes_show_vars():
    """System prompt describes SHOW_VARS() function."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "SHOW_VARS" in prompt


def test_system_prompt_describes_final_var():
    """System prompt describes FINAL_VAR() function."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "FINAL_VAR" in prompt


def test_iteration_zero_prompt_includes_step_by_step():
    """Iteration-0 prompt includes step-by-step instruction with question."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "step-by-step" in result.lower()
    assert "What color is the sky?" in result


def test_format_code_echo_wraps_output_with_boundary():
    """Code echo wraps REPL output when boundary is provided."""
    from ananta.rlm.prompts import format_code_echo

    result = format_code_echo("x = 1", "1", boundary="UNTRUSTED_CONTENT_abc123")
    assert "UNTRUSTED_CONTENT_abc123_BEGIN" in result
    assert "UNTRUSTED_CONTENT_abc123_END" in result
    assert "1" in result


def test_format_code_echo_no_wrapping_without_boundary():
    """Code echo does not wrap when boundary is None."""
    from ananta.rlm.prompts import format_code_echo

    result = format_code_echo("x = 1", "1")
    assert "_BEGIN" not in result
    assert "_END" not in result
    assert "REPL output:" in result


def test_system_prompt_contains_boundary_section():
    """System prompt includes security section when boundary is provided."""
    loader = PromptLoader()
    boundary = "UNTRUSTED_CONTENT_abc123"
    prompt = loader.render_system_prompt(boundary=boundary)
    assert "UNTRUSTED_CONTENT_abc123_BEGIN" in prompt
    assert "UNTRUSTED_CONTENT_abc123_END" in prompt
    assert "UNTRUSTED" in prompt
    assert "raw document data" in prompt.lower()


def test_system_prompt_no_boundary_section_by_default():
    """System prompt has no boundary section when no boundary is provided."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "_BEGIN" not in prompt
    assert "_END" not in prompt
