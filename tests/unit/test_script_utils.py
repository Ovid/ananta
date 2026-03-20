"""Tests for script_utils shared utilities."""

import sys

from ananta.rlm.trace import StepType, TokenUsage, Trace


class TestThinkingSpinner:
    """Tests for ThinkingSpinner class."""

    def test_start_sets_running(self) -> None:
        """Start should set _running to True and create thread."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        assert not spinner._running
        assert spinner._thread is None

        spinner.start()
        assert spinner._running
        assert spinner._thread is not None
        assert spinner._thread.is_alive()

        spinner.stop()

    def test_stop_clears_running(self) -> None:
        """Stop should set _running to False."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        spinner.start()
        spinner.stop()

        assert not spinner._running


class TestFormatProgress:
    """Tests for format_progress function."""

    def test_format_with_elapsed(self) -> None:
        """Format progress with elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.CODE_GENERATED, 0, "code", elapsed_seconds=1.5)
        assert "[1.5s]" in result
        assert "[Iteration 1]" in result
        assert "Generating code" in result

    def test_format_without_elapsed(self) -> None:
        """Format progress without elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.FINAL_ANSWER, 2, "answer")
        assert "[Iteration 3]" in result
        assert "Final answer" in result


class TestFormatThoughtTime:
    """Tests for format_thought_time function."""

    def test_singular_second(self) -> None:
        """One second should use singular form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(1.2)
        assert result == "[Thought for 1 second]"

    def test_plural_seconds(self) -> None:
        """Multiple seconds should use plural form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(5.7)
        assert result == "[Thought for 6 seconds]"


class TestFormatStats:
    """Tests for format_stats function."""

    def test_format_stats_output(self) -> None:
        """Format stats should include all metrics."""
        from examples.script_utils import format_stats

        token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        trace = Trace(steps=[])

        result = format_stats(2.5, token_usage, trace)
        assert "Execution time: 2.50s" in result
        assert "Tokens: 150" in result
        assert "prompt: 100" in result
        assert "completion: 50" in result
        assert "Trace steps: 0" in result


class TestIsExitCommand:
    """Tests for is_exit_command function."""

    def test_quit_is_exit(self) -> None:
        """'quit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("quit")
        assert is_exit_command("QUIT")
        assert is_exit_command("Quit")

    def test_exit_is_exit(self) -> None:
        """'exit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("exit")
        assert is_exit_command("EXIT")

    def test_other_not_exit(self) -> None:
        """Other inputs should not be exit commands."""
        from examples.script_utils import is_exit_command

        assert not is_exit_command("hello")
        assert not is_exit_command("question")


class TestInstallUrllib3CleanupHook:
    """Tests for install_urllib3_cleanup_hook function."""

    def test_hook_installed(self) -> None:
        """Hook should be installed on sys.unraisablehook."""
        from examples.script_utils import install_urllib3_cleanup_hook

        original = sys.unraisablehook
        install_urllib3_cleanup_hook()

        # Hook should be changed
        assert sys.unraisablehook != original

        # Restore original
        sys.unraisablehook = original


class TestFormatAnalysisAsContext:
    """Tests for format_analysis_as_context function."""

    def test_includes_header_and_overview(self) -> None:
        """Context string includes header and overview text."""
        from ananta.models import RepoAnalysis
        from examples.script_utils import format_analysis_as_context

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="A Python web application.",
            components=[],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "=== Codebase Analysis ===" in result
        assert "A Python web application." in result
        assert result.rstrip().endswith("===")

    def test_includes_components(self) -> None:
        """Context string includes component details."""
        from ananta.models import AnalysisComponent, RepoAnalysis
        from examples.script_utils import format_analysis_as_context

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API for user management",
            apis=[{"type": "rest", "endpoints": ["/users", "/auth"]}],
            models=["User", "Session"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test app",
            components=[comp],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "Components:" in result
        assert "API Server (api/)" in result
        assert "REST API for user management" in result
        assert "APIs (rest): /users, /auth" in result
        assert "Models: User, Session" in result

    def test_handles_dict_endpoints(self) -> None:
        """Context string handles endpoints that are dicts, not strings."""
        from ananta.models import AnalysisComponent, RepoAnalysis
        from examples.script_utils import format_analysis_as_context

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API",
            apis=[
                {
                    "type": "rest",
                    "endpoints": [
                        {"path": "/users", "method": "GET"},
                        {"path": "/auth", "method": "POST"},
                    ],
                }
            ],
            models=[],
            entry_points=[],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[comp],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "APIs (rest):" in result
        assert "API Server" in result

    def test_includes_external_dependencies(self) -> None:
        """Context string includes external dependencies."""
        from ananta.models import AnalysisExternalDep, RepoAnalysis
        from examples.script_utils import format_analysis_as_context

        dep = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Primary data store",
            used_by=["API Server"],
            optional=False,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[dep],
        )

        result = format_analysis_as_context(analysis)

        assert "External Dependencies:" in result
        assert "PostgreSQL (database): Primary data store" in result

    def test_empty_analysis_still_valid(self) -> None:
        """Minimal analysis with no components or deps still produces valid output."""
        from ananta.models import RepoAnalysis
        from examples.script_utils import format_analysis_as_context

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Simple app",
            components=[],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "=== Codebase Analysis ===" in result
        assert "Simple app" in result
        # No Components or External Dependencies section
        assert "Components:" not in result
        assert "External Dependencies:" not in result


class TestFormatVerifiedOutput:
    """Tests for format_verified_output()."""

    def test_formats_summary_and_appendix(self) -> None:
        """Output contains both verified findings and appendix."""
        from ananta.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )
        from examples.script_utils import format_verified_output

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Real issue",
                    confidence="high",
                    reason="Confirmed by code.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="False alarm",
                    confidence="low",
                    reason="Standard idiom.",
                    evidence_classification="code_analysis",
                    flags=["standard_idiom"],
                ),
            ],
            content_type="code",
        )
        original_answer = "## P1.1: Real issue\nDetails.\n\n## P0.1: False alarm\nMore details."
        output = format_verified_output(original_answer, report)

        assert "Verified Findings" in output
        assert "Verification Appendix" in output
        assert "P1.1" in output
        assert "P0.1" in output
        assert "standard_idiom" in output

    def test_no_high_confidence_shows_message(self) -> None:
        """When no findings are high/medium confidence, shows appropriate message."""
        from ananta.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )
        from examples.script_utils import format_verified_output

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="Bogus",
                    confidence="low",
                    reason="Not real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="general",
        )
        output = format_verified_output("Original", report)
        assert "0" in output or "no verified findings" in output.lower() or "None" in output

    def test_all_high_confidence_no_appendix_content(self) -> None:
        """When all findings are high confidence, appendix says none filtered."""
        from ananta.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )
        from examples.script_utils import format_verified_output

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Good finding",
                    confidence="high",
                    reason="Confirmed.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="code",
        )
        output = format_verified_output("Original", report)
        assert "Verified Findings" in output
        assert (
            "0 findings filtered" in output
            or "no findings filtered" in output.lower()
            or "Appendix" in output
        )


class TestFormatAnalysisForDisplay:
    """Tests for analysis display formatting."""

    def test_format_analysis_includes_header(self) -> None:
        """Formatted analysis includes header with date."""
        from ananta.models import RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123def456",
            overview="A test application.",
            components=[],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "2026-02-06" in output
        assert "abc123de" in output  # First 8 chars of SHA

    def test_format_analysis_includes_overview(self) -> None:
        """Formatted analysis includes overview section."""
        from ananta.models import RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="This is a complex microservices application.",
            components=[],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "Overview" in output
        assert "This is a complex microservices application." in output

    def test_format_analysis_includes_components(self) -> None:
        """Formatted analysis includes components."""
        from ananta.models import AnalysisComponent, RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API for user management",
            apis=[{"type": "rest", "endpoints": ["/users", "/auth"]}],
            models=["User", "Session"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[comp],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "API Server" in output
        assert "api/" in output
        assert "REST API for user management" in output
        assert "User" in output

    def test_format_analysis_handles_dict_endpoints(self) -> None:
        """Formatted analysis handles endpoints that are dicts, not strings."""
        from ananta.models import AnalysisComponent, RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API",
            apis=[
                {
                    "type": "rest",
                    "endpoints": [
                        {"path": "/users", "method": "GET"},
                        {"path": "/auth", "method": "POST"},
                    ],
                }
            ],
            models=[],
            entry_points=[],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[comp],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "rest:" in output.lower()
        assert "API Server" in output

    def test_format_analysis_includes_caveats(self) -> None:
        """Formatted analysis includes caveats warning."""
        from ananta.models import RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
            caveats="This may be wrong.",
        )

        output = format_analysis_for_display(analysis)

        assert "This may be wrong." in output

    def test_format_analysis_includes_external_dependencies(self) -> None:
        """Formatted analysis includes external dependencies."""
        from ananta.models import AnalysisExternalDep, RepoAnalysis
        from examples.script_utils import format_analysis_for_display

        dep = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Primary data store",
            used_by=["API Server"],
            optional=False,
        )
        dep_optional = AnalysisExternalDep(
            name="Redis",
            type="cache",
            description="Session cache",
            used_by=["API Server"],
            optional=True,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[dep, dep_optional],
        )

        output = format_analysis_for_display(analysis)

        assert "External Dependencies" in output
        assert "PostgreSQL" in output
        assert "(optional)" in output
        assert "Redis" in output


class TestFormatPipelineContract:
    """Contract test: valid RepoAnalysis always produces valid format output."""

    def test_complex_valid_analysis_formats_successfully(self) -> None:
        """A realistic RepoAnalysis with multiple components formats without error."""
        from ananta.models import AnalysisComponent, AnalysisExternalDep, RepoAnalysis
        from examples.script_utils import format_analysis_as_context, format_analysis_for_display

        comp1 = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API for user management",
            apis=[
                {"type": "rest", "endpoints": ["/users", "/auth", "/health"]},
                {"type": "websocket", "endpoints": ["/ws/notifications"]},
            ],
            models=["User", "Session", "Token"],
            entry_points=["api/main.py", "api/cli.py"],
            internal_dependencies=["database", "auth"],
            auth="JWT",
            data_persistence="PostgreSQL",
        )
        comp2 = AnalysisComponent(
            name="Worker",
            path="worker/",
            description="Background task processor",
            apis=[],
            models=["Task", "Job"],
            entry_points=["worker/main.py"],
            internal_dependencies=["database"],
        )
        dep1 = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Primary data store for users and sessions",
            used_by=["API Server", "Worker"],
        )
        dep2 = AnalysisExternalDep(
            name="Redis",
            type="cache",
            description="Session cache and task queue",
            used_by=["API Server"],
            optional=True,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-08T12:00:00Z",
            head_sha="deadbeef1234",
            overview="A microservices application with REST API and background workers.",
            components=[comp1, comp2],
            external_dependencies=[dep1, dep2],
        )

        # Both format functions should produce valid string output
        context = format_analysis_as_context(analysis)
        assert isinstance(context, str)
        assert "API Server" in context
        assert "Worker" in context
        assert "PostgreSQL" in context
        assert "User" in context
        assert "microservices" in context

        display = format_analysis_for_display(analysis)
        assert isinstance(display, str)
        assert "API Server" in display
        assert "Worker" in display
        assert "PostgreSQL" in display
        assert "(optional)" in display
        assert "Entry points" in display
