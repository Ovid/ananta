"""Tests for semantic verification module."""

import json

import pytest

from ananta.rlm.semantic_verification import (
    FindingVerification,
    SemanticVerificationReport,
    detect_content_type,
    gather_cited_documents,
    parse_verification_response,
)


class TestFindingVerification:
    """Tests for FindingVerification dataclass."""

    def test_construction(self) -> None:
        """FindingVerification stores all fields."""
        fv = FindingVerification(
            finding_id="F1",
            original_claim="The code uses async/await",
            confidence="high",
            reason="Found async keyword in source",
            evidence_classification="direct_quote",
        )
        assert fv.finding_id == "F1"
        assert fv.original_claim == "The code uses async/await"
        assert fv.confidence == "high"
        assert fv.reason == "Found async keyword in source"
        assert fv.evidence_classification == "direct_quote"
        assert fv.flags == []

    def test_flags_default_empty(self) -> None:
        """Flags defaults to empty list."""
        fv = FindingVerification(
            finding_id="F1",
            original_claim="claim",
            confidence="low",
            reason="reason",
            evidence_classification="unsupported",
        )
        assert fv.flags == []

    def test_flags_custom(self) -> None:
        """Flags can be set to a custom list."""
        fv = FindingVerification(
            finding_id="F1",
            original_claim="claim",
            confidence="medium",
            reason="reason",
            evidence_classification="inferred",
            flags=["speculative", "no_source"],
        )
        assert fv.flags == ["speculative", "no_source"]


class TestSemanticVerificationReport:
    """Tests for SemanticVerificationReport dataclass."""

    def test_construction(self) -> None:
        """SemanticVerificationReport stores findings and content_type."""
        findings = [
            FindingVerification(
                finding_id="F1",
                original_claim="claim1",
                confidence="high",
                reason="reason1",
                evidence_classification="direct_quote",
            ),
        ]
        report = SemanticVerificationReport(
            findings=findings,
            content_type="code",
        )
        assert len(report.findings) == 1
        assert report.content_type == "code"

    def test_high_confidence_filters_high_and_medium(self) -> None:
        """high_confidence returns findings with high or medium confidence."""
        findings = [
            FindingVerification(
                finding_id="F1",
                original_claim="claim1",
                confidence="high",
                reason="r1",
                evidence_classification="direct_quote",
            ),
            FindingVerification(
                finding_id="F2",
                original_claim="claim2",
                confidence="medium",
                reason="r2",
                evidence_classification="inferred",
            ),
            FindingVerification(
                finding_id="F3",
                original_claim="claim3",
                confidence="low",
                reason="r3",
                evidence_classification="unsupported",
            ),
        ]
        report = SemanticVerificationReport(findings=findings, content_type="general")
        high = report.high_confidence
        assert len(high) == 2
        assert high[0].finding_id == "F1"
        assert high[1].finding_id == "F2"

    def test_low_confidence_filters_only_low(self) -> None:
        """low_confidence returns only findings with low confidence."""
        findings = [
            FindingVerification(
                finding_id="F1",
                original_claim="claim1",
                confidence="high",
                reason="r1",
                evidence_classification="direct_quote",
            ),
            FindingVerification(
                finding_id="F2",
                original_claim="claim2",
                confidence="low",
                reason="r2",
                evidence_classification="unsupported",
            ),
            FindingVerification(
                finding_id="F3",
                original_claim="claim3",
                confidence="medium",
                reason="r3",
                evidence_classification="inferred",
            ),
        ]
        report = SemanticVerificationReport(findings=findings, content_type="general")
        low = report.low_confidence
        assert len(low) == 1
        assert low[0].finding_id == "F2"

    def test_empty_report_returns_empty_lists(self) -> None:
        """Empty report returns empty lists for both properties."""
        report = SemanticVerificationReport(findings=[], content_type="general")
        assert report.high_confidence == []
        assert report.low_confidence == []


class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_empty_list_returns_general(self) -> None:
        """Empty doc_names list returns 'general'."""
        assert detect_content_type([]) == "general"

    def test_majority_code_files_returns_code(self) -> None:
        """Returns 'code' when more than half of docs are code files."""
        assert detect_content_type(["main.py", "utils.py", "README.md"]) == "code"

    def test_majority_non_code_returns_general(self) -> None:
        """Returns 'general' when majority are not code files."""
        assert detect_content_type(["report.pdf", "notes.txt", "main.py"]) == "general"

    def test_perl_extensions_detected(self) -> None:
        """Perl .pm and .pl files are detected as code."""
        assert detect_content_type(["Foo.pm", "bar.pl", "Baz.t"]) == "code"

    def test_mixed_extensions_all_recognized(self) -> None:
        """Various code extensions are all recognized."""
        code_files = ["app.js", "lib.ts", "main.rs", "server.go", "App.java"]
        assert detect_content_type(code_files) == "code"

    def test_case_insensitive(self) -> None:
        """Extension matching is case-insensitive."""
        assert detect_content_type(["MAIN.PY", "Utils.JS", "readme.txt"]) == "code"

    def test_no_extension_not_code(self) -> None:
        """Files without extensions are not counted as code."""
        assert detect_content_type(["Makefile", "Dockerfile", "README"]) == "general"

    def test_exactly_half_returns_general(self) -> None:
        """Exactly half code files returns 'general' (strict majority)."""
        assert detect_content_type(["main.py", "README.md"]) == "general"


class TestGatherCitedDocuments:
    """Tests for gather_cited_documents()."""

    def test_gathers_cited_docs_excludes_uncited(self) -> None:
        """Only cited documents are gathered, uncited ones excluded."""
        answer = "According to Doc 0, the function works correctly."
        documents = ["Content of doc zero", "Content of doc one"]
        doc_names = ["main.py", "utils.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert "Content of doc zero" in result
        assert "Content of doc one" not in result

    def test_includes_doc_name_in_header(self) -> None:
        """Document name is included in the header."""
        answer = "See Doc 0 for details."
        documents = ["Some content"]
        doc_names = ["main.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert "### Document 0 (main.py)" in result

    def test_out_of_range_ids_skipped(self) -> None:
        """Out-of-range document IDs are silently skipped."""
        answer = "Doc 0 and Doc 99 are relevant."
        documents = ["Content of doc zero"]
        doc_names = ["main.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert "Content of doc zero" in result
        assert "99" not in result

    def test_no_citations_returns_empty_string(self) -> None:
        """No citations in the answer returns empty string."""
        answer = "No documents referenced here."
        documents = ["Content of doc zero"]
        doc_names = ["main.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert result == ""

    def test_context_n_pattern_works(self) -> None:
        """context[N] citation pattern is recognized."""
        answer = "I found in context[1] that the function returns None."
        documents = ["First doc", "Second doc"]
        doc_names = ["first.py", "second.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert "Second doc" in result
        assert "### Document 1 (second.py)" in result

    def test_doc_names_shorter_than_documents_uses_fallback(self) -> None:
        """When doc_names is shorter than documents, uses fallback name."""
        answer = "See Doc 0 and Doc 1 for details."
        documents = ["Content zero", "Content one"]
        doc_names = ["only_one.py"]
        result = gather_cited_documents(answer, documents, doc_names)
        assert "### Document 0 (only_one.py)" in result
        assert "### Document 1 (doc_1)" in result
        assert "Content one" in result

    def test_empty_doc_names_uses_fallback(self) -> None:
        """When doc_names is empty, uses fallback names for all docs."""
        answer = "Doc 0 is relevant."
        documents = ["Content zero"]
        doc_names: list[str] = []
        result = gather_cited_documents(answer, documents, doc_names)
        assert "### Document 0 (doc_0)" in result
        assert "Content zero" in result


class TestParseVerificationResponse:
    """Tests for parse_verification_response()."""

    def test_valid_json_response(self) -> None:
        """Parses a valid JSON response with one finding."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "Uses async/await",
                    "confidence": "high",
                    "reason": "Found in source",
                    "evidence_classification": "direct_quote",
                    "flags": ["verified"],
                }
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert len(result) == 1
        assert result[0].finding_id == "F1"
        assert result[0].confidence == "high"
        assert result[0].flags == ["verified"]

    def test_multiple_findings(self) -> None:
        """Parses response with multiple findings."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "claim1",
                    "confidence": "high",
                    "reason": "r1",
                    "evidence_classification": "direct_quote",
                    "flags": [],
                },
                {
                    "finding_id": "F2",
                    "original_claim": "claim2",
                    "confidence": "low",
                    "reason": "r2",
                    "evidence_classification": "unsupported",
                    "flags": ["speculative"],
                },
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert len(result) == 2
        assert result[0].finding_id == "F1"
        assert result[1].finding_id == "F2"
        assert result[1].flags == ["speculative"]

    def test_json_in_markdown_code_block(self) -> None:
        """Parses JSON wrapped in markdown code blocks."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "claim",
                    "confidence": "medium",
                    "reason": "reason",
                    "evidence_classification": "inferred",
                    "flags": [],
                }
            ]
        }
        text = f"Here is the result:\n```json\n{json.dumps(data)}\n```"
        result = parse_verification_response(text)
        assert len(result) == 1
        assert result[0].finding_id == "F1"

    def test_json_in_code_block_without_trailing_newline(self) -> None:
        """Parses JSON in code block when no newline before closing fence."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "claim",
                    "confidence": "high",
                    "reason": "reason",
                    "evidence_classification": "direct_quote",
                    "flags": [],
                }
            ]
        }
        text = f"```json\n{json.dumps(data)}```"
        result = parse_verification_response(text)
        assert len(result) == 1
        assert result[0].finding_id == "F1"

    def test_invalid_json_raises_value_error(self) -> None:
        """Raises ValueError when no valid JSON is found."""
        with pytest.raises(ValueError):
            parse_verification_response("This is not JSON at all")

    def test_missing_findings_key_raises_value_error(self) -> None:
        """Raises ValueError when JSON lacks 'findings' key."""
        with pytest.raises(ValueError):
            parse_verification_response(json.dumps({"results": []}))

    def test_missing_required_field_raises_value_error(self) -> None:
        """Raises ValueError when a finding is missing a required field."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "claim",
                    # missing "confidence", "reason", "evidence_classification"
                }
            ]
        }
        with pytest.raises(ValueError):
            parse_verification_response(json.dumps(data))

    def test_non_dict_finding_raises_value_error(self) -> None:
        """Raises ValueError when a finding entry is not a dict."""
        data = {"findings": ["not a dict", 42]}
        with pytest.raises(ValueError):
            parse_verification_response(json.dumps(data))

    def test_missing_flags_defaults_to_empty_list(self) -> None:
        """Missing flags field defaults to empty list."""
        data = {
            "findings": [
                {
                    "finding_id": "F1",
                    "original_claim": "claim",
                    "confidence": "high",
                    "reason": "reason",
                    "evidence_classification": "direct_quote",
                }
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert len(result) == 1
        assert result[0].flags == []
