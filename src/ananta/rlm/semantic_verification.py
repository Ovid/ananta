"""Semantic verification of RLM findings against source documents."""

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from shesha.rlm.verification import extract_citations


@dataclass
class FindingVerification:
    """Verification result for a single finding."""

    finding_id: str
    original_claim: str
    confidence: str
    reason: str
    evidence_classification: str
    flags: list[str] = field(default_factory=list)


@dataclass
class SemanticVerificationReport:
    """Report containing verified findings."""

    findings: list[FindingVerification]
    content_type: str

    @property
    def high_confidence(self) -> list[FindingVerification]:
        """Return findings where confidence is high or medium."""
        return [f for f in self.findings if f.confidence in ("high", "medium")]

    @property
    def low_confidence(self) -> list[FindingVerification]:
        """Return findings where confidence is low."""
        return [f for f in self.findings if f.confidence == "low"]


CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pl",
        ".pm",
        ".t",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".rb",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cc",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".clj",
        ".ex",
        ".exs",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".sql",
        ".r",
        ".m",
        ".mm",
        ".lua",
        ".vim",
        ".el",
        ".hs",
        ".php",
        ".dart",
        ".v",
        ".zig",
    }
)


def detect_content_type(doc_names: list[str]) -> str:
    """Detect whether documents are predominantly code or general content.

    Returns "code" if a strict majority of doc_names have code extensions,
    "general" otherwise. Empty list returns "general".
    """
    if not doc_names:
        return "general"
    code_count = sum(
        1 for name in doc_names if PurePosixPath(name).suffix.lower() in CODE_EXTENSIONS
    )
    if code_count > len(doc_names) / 2:
        return "code"
    return "general"


def gather_cited_documents(answer: str, documents: list[str], doc_names: list[str]) -> str:
    """Gather documents cited in the answer into a formatted string.

    Extracts citation IDs from the answer, looks up corresponding documents,
    and formats them with headers. Out-of-range IDs are silently skipped.
    Returns empty string if no valid citations are found.
    """
    cited_ids = extract_citations(answer)
    sections: list[str] = []
    for doc_id in cited_ids:
        if 0 <= doc_id < len(documents):
            name = doc_names[doc_id] if doc_id < len(doc_names) else f"doc_{doc_id}"
            header = f"### Document {doc_id} ({name})"
            sections.append(f"{header}\n\n{documents[doc_id]}")
    return "\n\n---\n\n".join(sections)


_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\s*```", re.DOTALL)


def _try_parse_findings(text: str) -> list[FindingVerification] | None:
    """Try to parse a JSON string as a findings structure.

    Returns a list of FindingVerification if text contains a valid
    {"findings": [...]} structure, None otherwise.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "findings" not in data:
        return None
    try:
        findings: list[FindingVerification] = []
        for item in data["findings"]:
            findings.append(
                FindingVerification(
                    finding_id=item["finding_id"],
                    original_claim=item["original_claim"],
                    confidence=item["confidence"],
                    reason=item["reason"],
                    evidence_classification=item["evidence_classification"],
                    flags=item.get("flags", []),
                )
            )
    except (KeyError, TypeError):
        return None
    return findings


def parse_verification_response(text: str) -> list[FindingVerification]:
    """Parse a verification response from an LLM into FindingVerification objects.

    Tries extracting JSON from markdown code blocks first, then individual
    JSON lines, then the full text. Raises ValueError if no valid JSON with
    a 'findings' key is found.
    """
    # Try markdown code blocks first
    for match in _CODE_BLOCK_RE.finditer(text):
        result = _try_parse_findings(match.group(1).strip())
        if result is not None:
            return result

    # Try individual lines
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("{"):
            result = _try_parse_findings(line)
            if result is not None:
                return result

    # Try full text
    result = _try_parse_findings(text.strip())
    if result is not None:
        return result

    raise ValueError("No valid verification JSON found in response")
