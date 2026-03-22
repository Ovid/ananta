"""Data models for the arXiv explorer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


@dataclass
class PaperMeta:
    """Metadata for a cached arXiv paper."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: datetime
    updated: datetime
    categories: list[str]
    primary_category: str
    pdf_url: str
    arxiv_url: str
    comment: str | None = None
    journal_ref: str | None = None
    doi: str | None = None
    source_type: str | None = None  # "latex", "pdf", or None if not yet downloaded

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "categories": self.categories,
            "primary_category": self.primary_category,
            "pdf_url": self.pdf_url,
            "arxiv_url": self.arxiv_url,
            "comment": self.comment,
            "journal_ref": self.journal_ref,
            "doi": self.doi,
            "source_type": self.source_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> PaperMeta:
        """Deserialize from a dict."""
        return cls(
            arxiv_id=str(d["arxiv_id"]),
            title=str(d["title"]),
            authors=[str(a) for a in d["authors"]],  # type: ignore[attr-defined]
            abstract=str(d["abstract"]),
            published=datetime.fromisoformat(str(d["published"])),
            updated=datetime.fromisoformat(str(d["updated"])),
            categories=[str(c) for c in d["categories"]],  # type: ignore[attr-defined]
            primary_category=str(d["primary_category"]),
            pdf_url=str(d["pdf_url"]),
            arxiv_url=str(d["arxiv_url"]),
            comment=str(d["comment"]) if d.get("comment") is not None else None,
            journal_ref=str(d["journal_ref"]) if d.get("journal_ref") is not None else None,
            doi=str(d["doi"]) if d.get("doi") is not None else None,
            source_type=str(d["source_type"]) if d.get("source_type") is not None else None,
        )


class VerificationStatus(Enum):
    """Status of a citation verification."""

    VERIFIED = "verified"
    VERIFIED_EXTERNAL = "verified_external"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"
    UNRESOLVED = "unresolved"  # Non-arXiv citation, cannot verify yet
    TOPICALLY_UNRELATED = "topically_unrelated"


@dataclass
class ExtractedCitation:
    """A citation extracted from a paper."""

    key: str
    title: str | None
    authors: list[str]
    year: str | None
    arxiv_id: str | None = None
    doi: str | None = None
    raw_text: str | None = None  # Original text of the citation entry


@dataclass
class VerificationResult:
    """Result of verifying a single citation."""

    citation_key: str
    status: VerificationStatus
    message: str | None = None
    actual_title: str | None = None
    arxiv_url: str | None = None
    severity: str | None = None  # "error" or "warning"; None for VERIFIED/UNRESOLVED
    source: str | None = None  # "arxiv", "crossref", "openalex", "semantic_scholar"


@dataclass
class TopicInfo:
    """Metadata about a topic for display in /history."""

    name: str
    created: datetime
    paper_count: int
    size_bytes: int
    project_id: str

    @property
    def formatted_size(self) -> str:
        """Human-readable size string using SI (base-10) units."""
        if self.size_bytes == 0:
            return "0 B"
        elif self.size_bytes < 1_000_000:
            return f"{self.size_bytes / 1000:.1f} KB"
        elif self.size_bytes < 1_000_000_000:
            return f"{self.size_bytes / 1_000_000:.1f} MB"
        else:
            return f"{self.size_bytes / 1_000_000_000:.1f} GB"


@dataclass
class CheckReport:
    """Full citation check report for one paper."""

    arxiv_id: str
    title: str
    citations: list[ExtractedCitation]
    verification_results: list[VerificationResult]
    llm_phrases: list[tuple[int, str]]  # (line_number, matched_phrase)

    @property
    def verified_count(self) -> int:
        """Count of verified citations."""
        return sum(
            1
            for r in self.verification_results
            if r.status in (VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_EXTERNAL)
        )

    @property
    def mismatch_count(self) -> int:
        """Count of mismatched or not-found citations."""
        return sum(
            1
            for r in self.verification_results
            if r.status in (VerificationStatus.MISMATCH, VerificationStatus.NOT_FOUND)
        )

    @property
    def unresolved_count(self) -> int:
        """Count of unresolved citations."""
        return sum(
            1 for r in self.verification_results if r.status == VerificationStatus.UNRESOLVED
        )


class CitationVerifier(Protocol):
    """Protocol for citation verifiers.

    Initial implementation: ArxivVerifier (arXiv API only).
    Future: CrossRefVerifier, SemanticScholarVerifier.
    """

    def verify(self, citation: ExtractedCitation) -> VerificationResult: ...
