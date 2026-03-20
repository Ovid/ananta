"""Randomized untrusted content boundaries for prompt injection defense."""

import secrets


def generate_boundary() -> str:
    """Generate a unique boundary token for a single query.

    Returns a token like UNTRUSTED_CONTENT_a8f3c2e9b1d4... with 128 bits
    of entropy (32 hex characters). Papers cannot forge a closing tag
    because the boundary is generated fresh per query and never persisted.
    """
    return f"UNTRUSTED_CONTENT_{secrets.token_hex(16)}"


def wrap_untrusted(content: str, boundary: str) -> str:
    """Wrap untrusted content with the query's boundary token."""
    return f"{boundary}_BEGIN\n{content}\n{boundary}_END"
