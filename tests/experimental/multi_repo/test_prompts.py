"""Tests for multi-repo prompt templates."""

from pathlib import Path


def test_recon_prompt_exists():
    """Recon prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "ananta"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "recon.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "APIs" in content or "apis" in content.lower()
    assert "models" in content.lower()


def test_impact_prompt_exists():
    """Impact prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "ananta"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "impact.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "PRD" in content
    assert "changes" in content.lower()


def test_synthesize_prompt_exists():
    """Synthesize prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "ananta"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "synthesize.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "HLD" in content or "design" in content.lower()


def test_align_prompt_exists():
    """Align prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "ananta"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "align.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "PRD" in content
    assert "gap" in content.lower() or "coverage" in content.lower()
