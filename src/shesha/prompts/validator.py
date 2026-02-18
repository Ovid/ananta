"""Prompt validation utilities."""

import re
from dataclasses import dataclass


@dataclass
class PromptSchema:
    """Schema for a prompt file."""

    required: set[str]
    optional: set[str]
    required_file: bool = True


PROMPT_SCHEMAS: dict[str, PromptSchema] = {
    "system.md": PromptSchema(
        required=set(),
        optional=set(),
    ),
    "context_metadata.md": PromptSchema(
        required={"context_type", "context_total_length", "context_lengths"},
        optional={"doc_names"},
    ),
    "subcall.md": PromptSchema(
        required={"instruction", "content"},
        optional=set(),
    ),
    "code_required.md": PromptSchema(
        required=set(),
        optional=set(),
    ),
    "iteration_zero.md": PromptSchema(
        required={"question"},
        optional=set(),
    ),
    "iteration_continue.md": PromptSchema(
        required={"question"},
        optional=set(),
    ),
    "verify_adversarial.md": PromptSchema(
        required={"findings", "documents"},
        optional=set(),
        required_file=False,
    ),
    "verify_code.md": PromptSchema(
        required={"previous_results", "findings", "documents"},
        optional=set(),
        required_file=False,
    ),
}


class PromptValidationError(Exception):
    """Raised when prompt validation fails."""

    pass


def validate_prompt(filename: str, content: str) -> None:
    """Validate a prompt file against its schema.

    Args:
        filename: Name of the prompt file (e.g., "system.md")
        content: Content of the prompt file

    Raises:
        PromptValidationError: If validation fails
    """
    if filename not in PROMPT_SCHEMAS:
        raise PromptValidationError(f"Unknown prompt file: {filename}")

    schema = PROMPT_SCHEMAS[filename]
    found = extract_placeholders(content)

    # Check for missing required placeholders
    missing = schema.required - found
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise PromptValidationError(
            f"{filename} is missing required placeholder: {{{missing_list}}}\n\n"
            f"Required placeholders for this file: {{{', '.join(sorted(schema.required))}}}"
        )

    # Check for unknown placeholders
    allowed = schema.required | schema.optional
    unknown = found - allowed
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise PromptValidationError(
            f"{filename} contains unknown placeholder: {{{unknown_list}}}\n\n"
            f"Available placeholders for this file: {{{', '.join(sorted(allowed))}}}"
        )


def extract_placeholders(text: str) -> set[str]:
    """Extract placeholder names from a template string.

    Handles both {name} and {name:format_spec} patterns.
    Ignores escaped braces ({{ and }}).
    """
    # Remove escaped braces to avoid false matches
    # Python's str.format uses {{ for literal { and }} for literal }
    cleaned = text.replace("{{", "").replace("}}", "")
    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}"
    matches = re.findall(pattern, cleaned)
    return set(matches)
