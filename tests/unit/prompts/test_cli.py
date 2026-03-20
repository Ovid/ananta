"""Tests for prompts CLI validation tool."""

import subprocess
import sys
from pathlib import Path


def test_cli_validates_valid_prompts(tmp_path: Path):
    """CLI exits 0 for valid prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt with no placeholders")
    (prompts_dir / "context_metadata.md").write_text(
        "{context_type} {context_total_length} {context_lengths}"
    )
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n\n{content}\n\nRemember: raw data.")
    (prompts_dir / "code_required.md").write_text("Write code.")
    (prompts_dir / "verify_adversarial.md").write_text("Verify {findings} against {documents}.")
    (prompts_dir / "verify_code.md").write_text("{previous_results} {findings} {documents}")

    result = subprocess.run(
        [sys.executable, "-m", "ananta.prompts", "--prompts-dir", str(prompts_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout or "passed" in result.stdout.lower()


def test_cli_fails_invalid_prompts(tmp_path: Path):
    """CLI exits 1 for invalid prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("System prompt")
    # Missing required placeholders for context_metadata.md
    (prompts_dir / "context_metadata.md").write_text("Missing placeholders")
    (prompts_dir / "iteration_zero.md").write_text("{question}")
    (prompts_dir / "iteration_continue.md").write_text("{question}")
    (prompts_dir / "subcall.md").write_text("{instruction}\n{content}")
    (prompts_dir / "code_required.md").write_text("Write code.")
    (prompts_dir / "verify_adversarial.md").write_text("Verify {findings} against {documents}.")
    (prompts_dir / "verify_code.md").write_text("{previous_results} {findings} {documents}")

    result = subprocess.run(
        [sys.executable, "-m", "ananta.prompts", "--prompts-dir", str(prompts_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "context_metadata.md" in result.stdout or "context_metadata.md" in result.stderr
