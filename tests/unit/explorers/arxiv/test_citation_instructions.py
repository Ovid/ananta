"""Tests for citation instruction builder."""

from unittest.mock import MagicMock

from ananta.explorers.arxiv.websockets import build_citation_instructions


def test_build_citation_instructions_single_paper() -> None:
    """Single paper produces instruction block with one entry."""
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "An Objective Bayesian Analysis"
    cache.get_meta.return_value = meta

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "An Objective Bayesian Analysis" in result
    assert "CITATION INSTRUCTIONS" in result


def test_build_citation_instructions_multiple_papers() -> None:
    """Multiple papers listed in instruction block."""
    cache = MagicMock()

    def fake_meta(arxiv_id: str) -> MagicMock:
        m = MagicMock()
        m.title = f"Title for {arxiv_id}"
        return m

    cache.get_meta.side_effect = fake_meta

    result = build_citation_instructions(["2005.09008v1", "2401.12345"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "[@arxiv:2401.12345]" in result
    assert "Title for 2005.09008v1" in result
    assert "Title for 2401.12345" in result


def test_build_citation_instructions_missing_meta_uses_id() -> None:
    """When cache has no metadata, fall back to arxiv_id as title."""
    cache = MagicMock()
    cache.get_meta.return_value = None

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    # Should still produce valid instructions even without title
    assert "2005.09008v1" in result


def test_build_citation_instructions_empty_list() -> None:
    """Empty paper list returns empty string."""
    cache = MagicMock()

    result = build_citation_instructions([], cache)

    assert result == ""


def test_citation_instructions_appended_to_question() -> None:
    """Verify that build_citation_instructions output follows expected structure.

    The actual wiring into _handle_query is integration-level (WebSocket +
    async + RLM engine), so we test the contract: the returned string starts
    with newlines and ends with the 'Always use' instruction.
    """
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "Test Paper"
    cache.get_meta.return_value = meta

    instructions = build_citation_instructions(["2005.09008v1"], cache)

    # Starts with newlines so it appends cleanly to a question
    assert instructions.startswith("\n\n")
    # Ends with the closing instruction
    expected_ending = "Always use [@arxiv:ID] when referencing a specific paper's claims or quotes."
    assert instructions.endswith(expected_ending)


def test_citation_instructions_require_one_id_per_tag() -> None:
    """Instructions must explicitly tell the LLM to use one ID per tag.

    LLMs sometimes generate [@arxiv:ID1; @arxiv:ID2] which breaks the
    frontend regex parser. The prompt must forbid this and show the
    correct multi-citation format.
    """
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "Test Paper"
    cache.get_meta.return_value = meta

    result = build_citation_instructions(["2005.09008v1"], cache)

    # Must explicitly forbid combining IDs in one tag
    assert "one" in result.lower() and "per" in result.lower(), (
        "Instructions must state 'one ID per tag' or similar"
    )
    # Must show the correct multi-citation format
    assert "][@arxiv:" in result, (
        "Instructions must show adjacent-tag format: [@arxiv:ID1][@arxiv:ID2]"
    )
