"""Post-FINAL citation verification for RLM answers."""

import json
import re
from dataclasses import dataclass


@dataclass
class Citation:
    """A document citation found in an answer."""

    doc_id: int
    found: bool


@dataclass
class Quote:
    """A quoted string found in an answer."""

    text: str
    doc_id: int
    found: bool


@dataclass
class VerificationResult:
    """Result of citation verification."""

    citations: list[Citation]
    quotes: list[Quote]

    @property
    def all_valid(self) -> bool:
        """True when all citations and quotes were found."""
        return all(c.found for c in self.citations) and all(q.found for q in self.quotes)


# Patterns for extracting doc citations from LLM answers
_CITATION_PATTERNS = [
    re.compile(r"\bDoc\s+\*\*(\d+)\*\*"),  # Doc **N**
    re.compile(r"\bDoc\s+(\d+)"),  # Doc N
    re.compile(r"\bcontext\[(\d+)\]"),  # context[N]
    re.compile(r"(?<!\w)\*\*(\d+)\*\*(?!\w)"),  # standalone **N**
]


def extract_citations(text: str) -> list[int]:
    """Extract unique doc IDs from an answer, preserving first-appearance order."""
    # Collect all matches with their text position across all patterns
    matches: list[tuple[int, int]] = []  # (position, doc_id)
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), int(match.group(1))))
    matches.sort()

    seen: set[int] = set()
    result: list[int] = []
    for _, doc_id in matches:
        if doc_id not in seen:
            seen.add(doc_id)
            result.append(doc_id)
    return result


_MIN_QUOTE_LENGTH = 10

# Patterns for extracting quoted evidence from LLM answers
_QUOTE_PATTERNS = [
    re.compile(rf'"([^"]{{{_MIN_QUOTE_LENGTH},}})"'),  # "double-quoted"
    re.compile(rf"`([^`]{{{_MIN_QUOTE_LENGTH},}})`"),  # `backtick-quoted`
]


def extract_quotes(text: str) -> list[str]:
    """Extract unique quoted strings (>= 10 chars) from an answer."""
    seen: set[str] = set()
    result: list[str] = []
    for pattern in _QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            quote = match.group(1)
            if quote not in seen:
                seen.add(quote)
                result.append(quote)
    return result


_MAX_QUOTE_CHECK_LEN = 60


def build_verification_code(answer: str) -> str:
    """Generate Python code that verifies citations in the sandbox.

    Runs extract_citations() and extract_quotes() on the host, then generates
    minimal Python that does context[N] lookups and substring checks in the
    sandbox where the context[] array is still loaded.
    """
    doc_ids = extract_citations(answer)
    quotes = extract_quotes(answer)

    # Truncate quotes for fuzzy substring matching
    truncated_quotes = [q[:_MAX_QUOTE_CHECK_LEN] for q in quotes]

    lines = [
        "import json",
        "",
        "citations = []",
        "quotes = []",
    ]

    # Check each cited doc ID exists
    for doc_id in doc_ids:
        lines.append("try:")
        lines.append(f"    _ = context[{doc_id}]")
        lines.append(f"    citations.append({{'doc_id': {doc_id}, 'found': True}})")
        lines.append("except (IndexError, NameError):")
        lines.append(f"    citations.append({{'doc_id': {doc_id}, 'found': False}})")

    # Check each quote as substring in all cited docs
    for quote_text in truncated_quotes:
        safe_quote = json.dumps(quote_text)
        lines.append(f"_q = {safe_quote}.lower()")
        lines.append("_found = False")
        lines.append("_found_in = -1")
        for doc_id in doc_ids:
            lines.append("try:")
            lines.append(f"    if not _found and _q in context[{doc_id}].lower():")
            lines.append("        _found = True")
            lines.append(f"        _found_in = {doc_id}")
            lines.append("except (IndexError, NameError):")
            lines.append("    pass")
        lines.append(
            f"quotes.append({{'text': {safe_quote}, 'doc_id': _found_in, 'found': _found}})"
        )

    lines.append("")
    lines.append("print(json.dumps({'citations': citations, 'quotes': quotes}))")

    return "\n".join(lines)


def parse_verification_output(stdout: str) -> VerificationResult:
    """Parse JSON verification output from sandbox execution.

    Scans stdout lines for a JSON object with 'citations' and 'quotes' keys.
    Raises ValueError if no valid verification JSON is found.
    """
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "citations" in data and "quotes" in data:
            citations = [Citation(doc_id=c["doc_id"], found=c["found"]) for c in data["citations"]]
            quotes = [
                Quote(text=q["text"], doc_id=q["doc_id"], found=q["found"]) for q in data["quotes"]
            ]
            return VerificationResult(citations=citations, quotes=quotes)

    raise ValueError("Could not parse verification output: no valid JSON found")
