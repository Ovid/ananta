"""Tests for PromptLoader."""

from pathlib import Path

import pytest

from shesha.prompts.loader import PromptLoader, resolve_prompts_dir
from shesha.prompts.validator import PromptValidationError


@pytest.fixture
def valid_prompts_dir(tmp_path: Path) -> Path:
    """Create a valid prompts directory."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt with no placeholders")
    (prompts_dir / "context_metadata.md").write_text(
        "Context is a {context_type} with {context_total_length} chars:"
        " {context_lengths}\nDocs: {doc_names}"
    )
    (prompts_dir / "iteration_zero.md").write_text("Safeguard: {question}")
    (prompts_dir / "iteration_continue.md").write_text("Continue: {question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code now.")
    (prompts_dir / "verify_adversarial.md").write_text(
        "Verify {findings} against {documents}. JSON: {{{{ }}}}"
    )
    (prompts_dir / "verify_code.md").write_text(
        "Previous: {previous_results}\nFindings: {findings}\nDocs: {documents}\nJSON: {{{{ }}}}"
    )

    return prompts_dir


def test_loader_loads_from_directory(valid_prompts_dir: Path):
    """PromptLoader loads prompts from specified directory."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    assert loader.prompts_dir == valid_prompts_dir


def test_loader_validates_on_init(tmp_path: Path):
    """PromptLoader validates prompts on initialization."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt")
    # Missing required placeholder (context_type)
    (prompts_dir / "context_metadata.md").write_text("Missing placeholders")
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code.")

    with pytest.raises(PromptValidationError) as exc_info:
        PromptLoader(prompts_dir=prompts_dir)
    assert "context_metadata.md" in str(exc_info.value)


def test_loader_render_system_prompt(valid_prompts_dir: Path):
    """PromptLoader renders system prompt (no variables)."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_system_prompt()
    assert isinstance(result, str)
    assert len(result) > 0


def test_system_prompt_unescapes_double_braces():
    """System prompt {{var}} examples render as {var} for valid Python."""
    loader = PromptLoader()
    result = loader.render_system_prompt()
    # The prompt contains f-string examples like f"...{chunk}..."
    # These are stored as {{chunk}} in the template but must be
    # unescaped to {chunk} when shown to the LLM
    assert "{{" not in result, (
        "System prompt contains escaped double braces that should be unescaped"
    )


def test_loader_render_context_metadata(valid_prompts_dir: Path):
    """PromptLoader renders context metadata with new variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_context_metadata(
        context_type="list",
        context_total_length=10000,
        context_lengths="[5000, 5000]",
        doc_names=["doc_0", "doc_1"],
    )
    assert "list" in result
    assert "10000" in result
    assert "[5000, 5000]" in result


def test_loader_render_context_metadata_includes_doc_names(valid_prompts_dir: Path):
    """PromptLoader renders context metadata with document names."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_context_metadata(
        context_type="list",
        context_total_length=5000,
        context_lengths="[2500, 2500]",
        doc_names=["README.md", "src/main.py"],
    )
    assert "README.md" in result
    assert "src/main.py" in result


def test_loader_render_iteration_zero(valid_prompts_dir: Path):
    """PromptLoader renders iteration-0 safeguard with question."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_iteration_zero(question="What is this?")
    assert "What is this?" in result


def test_loader_render_subcall_prompt(valid_prompts_dir: Path):
    """PromptLoader renders subcall prompt with variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_subcall_prompt(
        instruction="Summarize this",
        content="Document content here",
    )
    assert "Summarize this" in result
    assert "Document content here" in result


def test_loader_render_code_required(valid_prompts_dir: Path):
    """PromptLoader renders code_required prompt."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_code_required()
    assert "Write code" in result


def test_resolve_prompts_dir_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """resolve_prompts_dir uses SHESHA_PROMPTS_DIR env var."""
    monkeypatch.setenv("SHESHA_PROMPTS_DIR", str(tmp_path))
    result = resolve_prompts_dir()
    assert result == tmp_path


def test_loader_raises_when_directory_missing(tmp_path: Path):
    """PromptLoader raises FileNotFoundError for missing directory."""
    missing_dir = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError) as exc_info:
        PromptLoader(prompts_dir=missing_dir)
    assert "Prompts directory not found" in str(exc_info.value)


def test_loader_raises_when_file_missing(tmp_path: Path):
    """PromptLoader raises FileNotFoundError for missing prompt file."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    # Only create some files, not all
    (prompts_dir / "system.md").write_text("System prompt")

    with pytest.raises(FileNotFoundError) as exc_info:
        PromptLoader(prompts_dir=prompts_dir)
    assert "Required prompt file not found" in str(exc_info.value)


def test_loader_succeeds_without_optional_verify_files(tmp_path: Path):
    """PromptLoader loads successfully when optional verify templates are absent."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt")
    (prompts_dir / "context_metadata.md").write_text(
        "{context_type} {context_total_length} {context_lengths}"
    )
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code now.")

    # Should NOT raise — verify templates are optional
    loader = PromptLoader(prompts_dir=prompts_dir)
    assert loader.prompts_dir == prompts_dir


def test_loader_render_verify_adversarial_raises_when_not_loaded(tmp_path: Path):
    """render_verify_adversarial_prompt raises when template was not loaded."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt")
    (prompts_dir / "context_metadata.md").write_text(
        "{context_type} {context_total_length} {context_lengths}"
    )
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code.")

    loader = PromptLoader(prompts_dir=prompts_dir)
    with pytest.raises(FileNotFoundError, match="verify_adversarial.md"):
        loader.render_verify_adversarial_prompt(findings="f", documents="d")


def test_loader_render_verify_code_raises_when_not_loaded(tmp_path: Path):
    """render_verify_code_prompt raises when template was not loaded."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt")
    (prompts_dir / "context_metadata.md").write_text(
        "{context_type} {context_total_length} {context_lengths}"
    )
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code.")

    loader = PromptLoader(prompts_dir=prompts_dir)
    with pytest.raises(FileNotFoundError, match="verify_code.md"):
        loader.render_verify_code_prompt(previous_results="p", findings="f", documents="d")


def test_loader_loads_verify_adversarial(valid_prompts_dir: Path):
    """PromptLoader loads verify_adversarial.md template."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    raw = loader.get_raw_template("verify_adversarial.md")
    assert "{findings}" in raw
    assert "{documents}" in raw


def test_loader_render_verify_adversarial_prompt(valid_prompts_dir: Path):
    """PromptLoader renders verify_adversarial prompt with variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_verify_adversarial_prompt(
        findings="Finding 1: something wrong",
        documents="Document A content",
    )
    assert "Finding 1: something wrong" in result
    assert "Document A content" in result
    # Escaped braces should become literal braces after rendering
    assert "{{ }}" in result


def test_loader_loads_verify_code(valid_prompts_dir: Path):
    """PromptLoader loads verify_code.md template."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    raw = loader.get_raw_template("verify_code.md")
    assert "{previous_results}" in raw
    assert "{findings}" in raw
    assert "{documents}" in raw


def test_loader_render_verify_code_prompt(valid_prompts_dir: Path):
    """PromptLoader renders verify_code prompt with variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_verify_code_prompt(
        previous_results="Previous review JSON here",
        findings="Finding 2: code issue",
        documents="def foo(): pass",
    )
    assert "Previous review JSON here" in result
    assert "Finding 2: code issue" in result
    assert "def foo(): pass" in result
    # Escaped braces should become literal braces after rendering
    assert "{{ }}" in result


def test_loader_render_iteration_continue(valid_prompts_dir: Path):
    """PromptLoader renders iteration_continue prompt with question."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_iteration_continue(question="What is the answer?")
    assert "What is the answer?" in result


def test_system_prompt_contains_document_only_constraint():
    """System prompt must explicitly forbid using training data."""
    loader = PromptLoader()
    result = loader.render_system_prompt()
    assert "ONLY using information found in the provided context documents" in result
    assert "do not introduce facts from your training data" in result
