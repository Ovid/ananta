"""RLM engine - the core REPL+LLM loop."""

import ast
import copy
import json
import keyword
import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shesha.llm.client import LLMClient, LLMClientFactory
from shesha.models import QueryContext
from shesha.prompts import PromptLoader
from shesha.rlm.boundary import generate_boundary, wrap_untrusted
from shesha.rlm.prompts import (
    format_code_echo,
    truncate_code_output,
)
from shesha.rlm.semantic_verification import (
    SemanticVerificationReport,
    detect_content_type,
    gather_cited_documents,
    parse_verification_response,
)
from shesha.rlm.trace import StepType, TokenUsage, Trace, TraceStep
from shesha.rlm.trace_writer import IncrementalTraceWriter, TraceWriter
from shesha.rlm.verification import (
    VerificationResult,
    build_verification_code,
    parse_verification_output,
)
from shesha.sandbox.base import SandboxExecutor
from shesha.sandbox.executor import ContainerExecutor, ExecutionResult, SubcallContentError
from shesha.sandbox.pool import ContainerPool
from shesha.storage.base import StorageBackend

logger = logging.getLogger(__name__)

# Callback type for progress notifications
ProgressCallback = Callable[[StepType, int, str, TokenUsage], None]


@dataclass
class QueryResult:
    """Result of an RLM query."""

    answer: str
    trace: Trace
    token_usage: TokenUsage
    execution_time: float
    verification: VerificationResult | None = field(default=None)
    semantic_verification: SemanticVerificationReport | None = field(default=None)


def extract_code_blocks(text: str) -> list[str]:
    """Extract code from ```repl blocks."""
    pattern = r"```repl\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


def _is_python_identifier(s: str) -> bool:
    """Check if a string is a valid Python identifier (variable name).

    Used by find_final_answer to distinguish FINAL(variable_name) from
    FINAL(literal text). Python keywords like "True"/"False" are excluded
    because they are more likely literal values than variable names.
    """
    return s.isidentifier() and not keyword.iskeyword(s)


def _strip_string_quotes(content: str) -> str:
    """Strip surrounding quotes from a FINAL() argument if it looks like a Python string.

    When the model writes bare-text ``FINAL("some answer\\nwith newlines")``,
    the regex captures the quotes and literal ``\\n`` as-is.  This helper
    detects that pattern and evaluates the content as a Python string literal
    to recover the actual text with proper newlines and no wrapping quotes.
    """
    if (content.startswith('"') and content.endswith('"')) or (
        content.startswith("'") and content.endswith("'")
    ):
        try:
            evaluated = ast.literal_eval(content)
            if isinstance(evaluated, str):
                return evaluated
        except (ValueError, SyntaxError):
            pass  # Malformed string — return as-is
    return content


def find_final_answer(text: str) -> tuple[str, str] | None:
    """Find bare FINAL(...) or FINAL_VAR(...) in response text outside code blocks.

    Matches the reference RLM's find_final_answer (rlm/rlm/utils/parsing.py:29-63).
    The model sometimes outputs FINAL_VAR(x) as bare text instead of inside a
    ```repl block. This function catches those cases.

    **Important: FINAL(identifier) heuristic**

    When the LLM writes FINAL(x) as bare text, this function must decide
    whether x is a literal answer string or a Python variable name. Inside a
    ```repl code block, FINAL(x) is executed as Python and x is naturally
    resolved as a variable. But the bare-text regex parser has no Python
    runtime — it just captures the text between the parentheses.

    This caused a real bug (trace 2026-02-10T11-03-50): the LLM stored a
    38K-char audit report in a variable called `final_answer`, then wrote
    bare text `FINAL(final_answer)`. The parser returned ("final",
    "final_answer") — treating the variable name as the literal answer. The
    user saw just the word "final_answer" instead of the full report.

    The fix: when the captured content of FINAL(...) is a bare Python
    identifier (no quotes, no spaces, no operators — just a valid variable
    name), we treat it as a variable reference and return ("final_var", name)
    so the engine retrieves the value from the sandbox. Quoted strings,
    numbers, expressions, and sentences are still treated as literal answers.

    Returns:
        ("final", answer_string) for FINAL(...) with literal content
        ("final_var", variable_name) for FINAL_VAR(...) or FINAL(identifier)
        None if no pattern found
    """
    # Strip code blocks so we don't match FINAL inside ```repl blocks
    # (those are handled by the executor)
    stripped = re.sub(r"```repl\s*\n.*?\n```", "", text, flags=re.DOTALL)

    # Check FINAL_VAR first (more specific pattern)
    final_var_pattern = r"^\s*FINAL_VAR\((.*?)\)"
    match = re.search(final_var_pattern, stripped, re.MULTILINE | re.DOTALL)
    if match:
        var_name = match.group(1).strip().strip('"').strip("'")
        if _is_python_identifier(var_name):
            return ("final_var", var_name)
        return ("final", var_name)

    # Check FINAL pattern — greedy match to handle nested parentheses,
    # no quote requirement (aligned with reference RLM rlm/utils/parsing.py:58)
    final_pattern = r"^\s*FINAL\((.*)\)\s*$"
    match = re.search(final_pattern, stripped, re.MULTILINE | re.DOTALL)
    if match:
        content = match.group(1).strip()
        # Heuristic: if the content is a bare Python identifier (valid variable
        # name, no quotes, no spaces, no operators), the LLM almost certainly
        # meant to reference a sandbox variable — not return the identifier
        # itself as a literal answer. Treat it as a variable reference so the
        # engine retrieves the actual value from the sandbox.
        #
        # Examples:
        #   FINAL(final_answer) → ("final_var", "final_answer")  # variable ref
        #   FINAL("the answer")  → ("final", "the answer")       # quotes stripped
        #   FINAL(42)            → ("final", "42")                # literal
        #   FINAL(x + y)         → ("final", "x + y")            # literal
        if _is_python_identifier(content):
            return ("final_var", content)
        return ("final", _strip_string_quotes(content))

    return None


@dataclass
class _CodeBlockResult:
    """Result of executing code blocks within a single iteration."""

    final_answer: str | None
    all_output: list[str]
    exec_results: list[ExecutionResult]
    failed_final_var: str | None = None


class RLMEngine:
    """The RLM engine - runs the REPL+LLM loop."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_iterations: int = 20,
        # 20K per-block limit matches reference RLM (rlm/rlm/utils/parsing.py:67).
        # This is a forcing function: when context exceeds the truncation limit,
        # the model must use llm_query() to analyze content it cannot see.
        max_output_chars: int = 20_000,
        execution_timeout: int = 30,
        max_subcall_content_chars: int = 500_000,
        prompts_dir: Path | None = None,
        pool: ContainerPool | None = None,
        max_traces_per_project: int = 50,
        verify_citations: bool = True,
        verify: bool = False,
        llm_client_factory: LLMClientFactory | None = None,
    ) -> None:
        """Initialize the RLM engine."""
        self.model = model
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.max_output_chars = max_output_chars
        self.execution_timeout = execution_timeout
        self.max_subcall_content_chars = max_subcall_content_chars
        self.prompt_loader = PromptLoader(prompts_dir)
        self._pool = pool
        self.max_traces_per_project = max_traces_per_project
        self.verify_citations = verify_citations
        self.verify = verify
        self._llm_client_factory: LLMClientFactory = llm_client_factory or LLMClient
        self._subcall_lock = threading.Lock()

    @property
    def pool(self) -> ContainerPool | None:
        """The container pool used for query execution, or None."""
        return self._pool

    @property
    def llm_client_factory(self) -> LLMClientFactory:
        """The factory callable used to create LLM clients."""
        return self._llm_client_factory

    def set_pool(self, pool: ContainerPool | None) -> None:
        """Set or clear the container pool used for query execution.

        Args:
            pool: A ContainerPool instance, or None to clear.
        """
        self._pool = pool

    def _handle_llm_query(
        self,
        instruction: str,
        content: str,
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
        on_step: Callable[[TraceStep], None] | None = None,
        *,
        boundary: str,
    ) -> str:
        """Handle a sub-LLM query from the sandbox.

        Thread-safe: uses _subcall_lock to protect shared trace and token state
        when called concurrently from batched executor dispatch.
        """
        # Record the request (lock protects trace and token_usage mutations)
        step_content = f"instruction: {instruction}\ncontent: [{len(content)} chars]"
        with self._subcall_lock:
            step = trace.add_step(
                type=StepType.SUBCALL_REQUEST,
                content=step_content,
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SUBCALL_REQUEST, iteration, step_content, copy.copy(token_usage)
                )

        # Check size limit on the total payload (instruction + content).
        # Single-arg llm_query passes everything in instruction with content="",
        # so checking content alone would miss oversized single-arg calls.
        payload_size = len(instruction) + len(content)
        if payload_size > self.max_subcall_content_chars:
            error_msg = (
                f"Payload size ({payload_size:,} chars) exceeds the sub-LLM limit "
                f"of {self.max_subcall_content_chars:,} chars. Please chunk the content "
                f"into smaller pieces and make multiple llm_query calls."
            )
            with self._subcall_lock:
                step = trace.add_step(
                    type=StepType.SUBCALL_RESPONSE,
                    content=error_msg,
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.SUBCALL_RESPONSE, iteration, error_msg, copy.copy(token_usage)
                    )
            raise SubcallContentError(error_msg)

        # Build prompt: when content is empty (single-arg llm_query), send
        # instruction directly. When content is provided, wrap in untrusted tags.
        if content:
            wrapped_content = wrap_untrusted(content, boundary)
            prompt = self.prompt_loader.render_subcall_prompt(instruction, wrapped_content)
        else:
            prompt = instruction

        # LLM call runs outside lock — this is the I/O-bound work we parallelize
        sub_llm = self._llm_client_factory(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])

        # Record response and update tokens (lock protects shared state)
        with self._subcall_lock:
            token_usage.prompt_tokens += response.prompt_tokens
            token_usage.completion_tokens += response.completion_tokens

            step = trace.add_step(
                type=StepType.SUBCALL_RESPONSE,
                content=response.content,
                iteration=iteration,
                tokens_used=response.total_tokens,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SUBCALL_RESPONSE, iteration, response.content, copy.copy(token_usage)
                )

        return response.content

    def _run_semantic_verification(
        self,
        final_answer: str,
        documents: list[str],
        doc_names: list[str],
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
        on_step: Callable[[TraceStep], None] | None = None,
        *,
        boundary: str,
    ) -> SemanticVerificationReport | None:
        """Run semantic verification on the final answer.

        Returns SemanticVerificationReport or None if verification fails.
        """
        # Gather cited documents
        cited_docs_text = gather_cited_documents(final_answer, documents, doc_names)
        if not cited_docs_text:
            return None

        # Check cited docs size limit
        if len(cited_docs_text) > self.max_subcall_content_chars:
            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content=(
                    f"Skipping verification: cited documents ({len(cited_docs_text):,} chars) "
                    f"exceed limit of {self.max_subcall_content_chars:,} chars"
                ),
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            return None

        # Wrap cited docs in untrusted content tags (security boundary)
        wrapped_docs = wrap_untrusted(cited_docs_text, boundary)

        # Layer 1: Adversarial verification
        prompt = self.prompt_loader.render_verify_adversarial_prompt(
            findings=final_answer,
            documents=wrapped_docs,
        )

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content="Starting adversarial verification (Layer 1)",
            iteration=iteration,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(
                StepType.SEMANTIC_VERIFICATION,
                iteration,
                "Adversarial verification",
                copy.copy(token_usage),
            )

        sub_llm = self._llm_client_factory(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])
        token_usage.prompt_tokens += response.prompt_tokens
        token_usage.completion_tokens += response.completion_tokens

        findings = parse_verification_response(response.content)

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content=f"Layer 1 complete: {len(findings)} findings reviewed",
            iteration=iteration,
            tokens_used=response.total_tokens,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(
                StepType.SEMANTIC_VERIFICATION,
                iteration,
                f"Layer 1 complete: {len(findings)} findings",
                copy.copy(token_usage),
            )

        # Layer 2: Code-specific checks (only for code projects)
        content_type = detect_content_type(doc_names)
        if content_type == "code":
            layer1_json = json.dumps(
                {
                    "findings": [
                        {
                            "finding_id": f.finding_id,
                            "original_claim": f.original_claim,
                            "confidence": f.confidence,
                            "reason": f.reason,
                            "evidence_classification": f.evidence_classification,
                            "flags": f.flags,
                        }
                        for f in findings
                    ]
                },
                indent=2,
            )

            prompt = self.prompt_loader.render_verify_code_prompt(
                previous_results=layer1_json,
                findings=final_answer,
                documents=wrapped_docs,
            )

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content="Starting code-specific verification (Layer 2)",
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION,
                    iteration,
                    "Code-specific verification",
                    copy.copy(token_usage),
                )

            sub_llm2 = self._llm_client_factory(model=self.model, api_key=self.api_key)
            response2 = sub_llm2.complete(messages=[{"role": "user", "content": prompt}])
            token_usage.prompt_tokens += response2.prompt_tokens
            token_usage.completion_tokens += response2.completion_tokens

            findings = parse_verification_response(response2.content)

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content=f"Layer 2 complete: {len(findings)} findings reviewed",
                iteration=iteration,
                tokens_used=response2.total_tokens,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION,
                    iteration,
                    f"Layer 2 complete: {len(findings)} findings",
                    copy.copy(token_usage),
                )

        return SemanticVerificationReport(
            findings=findings,
            content_type=content_type,
        )

    def _execute_code_blocks(
        self,
        code_blocks: list[str],
        executor: SandboxExecutor,
        trace: Trace,
        iteration: int,
        token_usage: TokenUsage,
        on_progress: ProgressCallback | None,
        on_step: Callable[[TraceStep], None] | None,
    ) -> _CodeBlockResult:
        """Execute code blocks and check for FINAL answer.

        Returns a _CodeBlockResult with the final answer (if found),
        all output strings, and raw execution results.
        """
        all_output: list[str] = []
        exec_results: list[ExecutionResult] = []
        final_answer: str | None = None
        failed_final_var: str | None = None

        for code in code_blocks:
            exec_start = time.time()
            result = executor.execute(code, timeout=self.execution_timeout)
            exec_duration = int((time.time() - exec_start) * 1000)

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"STDERR: {result.stderr}")
            if result.error:
                output_parts.append(f"ERROR: {result.error}")

            output = "\n".join(output_parts) if output_parts else "(no output)"
            output = truncate_code_output(output, self.max_output_chars)

            step = trace.add_step(
                type=StepType.CODE_OUTPUT,
                content=output,
                iteration=iteration,
                duration_ms=exec_duration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(StepType.CODE_OUTPUT, iteration, output, copy.copy(token_usage))

            all_output.append(output)
            exec_results.append(result)

            # Check for final answer (use `is not None` to catch falsy
            # values like FINAL(0), FINAL(""), FINAL(False))
            if result.final_answer is not None:
                final_answer = (
                    result.final_answer
                    if isinstance(result.final_answer, str)
                    else str(result.final_answer)
                )
                step = trace.add_step(
                    type=StepType.FINAL_ANSWER,
                    content=final_answer,
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.FINAL_ANSWER,
                        iteration,
                        final_answer,
                        copy.copy(token_usage),
                    )
                break
            elif result.final_var is not None:
                resolved = result.final_value
                if resolved is None:
                    # Sandbox returned the variable name but not its value.
                    # Try resolving it explicitly; if that also fails, let
                    # the loop continue so the model can retry (matching the
                    # bare-text FINAL_VAR retry in the main query loop).
                    resolved = self._resolve_final_var(result.final_var, executor)
                if resolved is None:
                    # Variable truly not found — record for retry guidance
                    failed_final_var = result.final_var
                    break
                final_answer = resolved
                step = trace.add_step(
                    type=StepType.FINAL_ANSWER,
                    content=final_answer,
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.FINAL_ANSWER,
                        iteration,
                        final_answer,
                        copy.copy(token_usage),
                    )
                break

        return _CodeBlockResult(
            final_answer=final_answer,
            all_output=all_output,
            exec_results=exec_results,
            failed_final_var=failed_final_var,
        )

    def _resolve_final_var(
        self,
        var_name: str,
        executor: SandboxExecutor,
    ) -> str | None:
        """Resolve a FINAL_VAR variable from the sandbox.

        Returns the variable value as a string, or None if the variable
        was not found.
        """
        result = executor.execute(f"print({var_name})", timeout=self.execution_timeout)
        if result.status == "ok":
            return result.stdout.strip()
        return None

    def _run_verifications(
        self,
        final_answer: str,
        executor: SandboxExecutor,
        documents: list[str],
        doc_names: list[str],
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None,
        on_step: Callable[[TraceStep], None] | None,
        *,
        boundary: str,
    ) -> tuple[VerificationResult | None, SemanticVerificationReport | None]:
        """Run citation and semantic verification on a final answer.

        Returns (verification, semantic_verification) tuple.
        """
        verification = None
        if self.verify_citations and executor.is_alive:
            try:
                code = build_verification_code(final_answer)
                vresult = executor.execute(code, timeout=self.execution_timeout)
                if vresult.status == "ok" and vresult.stdout:
                    verification = parse_verification_output(vresult.stdout)
                    step = trace.add_step(
                        type=StepType.VERIFICATION,
                        content=vresult.stdout,
                        iteration=iteration,
                    )
                    if on_step:
                        on_step(step)
                    if on_progress:
                        on_progress(
                            StepType.VERIFICATION,
                            iteration,
                            vresult.stdout,
                            copy.copy(token_usage),
                        )
            except Exception as exc:
                step = trace.add_step(
                    type=StepType.VERIFICATION,
                    content=f"Verification error: {exc}",
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.VERIFICATION,
                        iteration,
                        f"Verification error: {exc}",
                        copy.copy(token_usage),
                    )

        semantic_verification = None
        if self.verify:
            try:
                semantic_verification = self._run_semantic_verification(
                    final_answer=final_answer,
                    documents=documents,
                    doc_names=doc_names,
                    trace=trace,
                    token_usage=token_usage,
                    iteration=iteration,
                    on_progress=on_progress,
                    on_step=on_step,
                    boundary=boundary,
                )
            except Exception as exc:
                step = trace.add_step(
                    type=StepType.SEMANTIC_VERIFICATION,
                    content=f"Semantic verification error: {exc}",
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.SEMANTIC_VERIFICATION,
                        iteration,
                        f"Semantic verification error: {exc}",
                        copy.copy(token_usage),
                    )

        return verification, semantic_verification

    def query(
        self,
        documents: list[str],
        question: str,
        doc_names: list[str] | None = None,
        on_progress: ProgressCallback | None = None,
        storage: StorageBackend | None = None,
        project_id: str | None = None,
        cancel_event: threading.Event | None = None,
        allow_background_knowledge: bool = False,
    ) -> QueryResult:
        """Run an RLM query against documents."""
        logger.info(
            "Starting query (model=%s, docs=%d, project=%s)",
            self.model,
            len(documents),
            project_id,
        )
        start_time = time.time()
        trace = Trace()
        token_usage = TokenUsage()
        boundary = generate_boundary()

        if doc_names is None:
            doc_names = [f"doc_{i}" for i in range(len(documents))]

        # Build system prompt (no variables — 500K hardcoded in template)
        doc_sizes = [len(d) for d in documents]
        total_chars = sum(doc_sizes)

        system_prompt = self.prompt_loader.render_system_prompt(
            boundary=boundary, augmented=allow_background_knowledge
        )

        # Context metadata as assistant message: primes the model to
        # continue working rather than start fresh. Matches reference
        # rlm/rlm/utils/prompts.py:119-122.
        # Always "list" — the sandbox sets context as list[str] regardless of count.
        # Matches reference RLM (rlm/core/types.py:244-245).
        context_type = "list"
        context_lengths = str(doc_sizes)
        context_metadata = self.prompt_loader.render_context_metadata(
            context_type=context_type,
            context_total_length=total_chars,
            context_lengths=context_lengths,
            doc_names=doc_names,
        )

        # Set up incremental trace writer
        inc_writer = (
            IncrementalTraceWriter(storage, suppress_errors=True) if storage is not None else None
        )
        if inc_writer is not None and project_id is not None:
            trace_id = str(uuid.uuid4())
            context = QueryContext(
                trace_id=trace_id,
                question=question,
                document_ids=doc_names or [f"doc_{i}" for i in range(len(documents))],
                model=self.model,
                system_prompt=system_prompt,
                subcall_prompt=self.prompt_loader.get_raw_template("subcall.md"),
            )
            inc_writer.start(project_id, context)

        def _write_step(step: TraceStep) -> None:
            if inc_writer is not None:
                inc_writer.write_step(step)

        def _finalize_trace_and_cleanup(answer: str, status: str) -> None:
            if inc_writer is None or inc_writer.finalized:
                return
            inc_writer.finalize(
                answer=answer,
                token_usage=token_usage,
                execution_time=time.time() - start_time,
                status=status,
            )
            if storage is not None and project_id is not None:
                TraceWriter(storage, suppress_errors=True).cleanup_old_traces(
                    project_id, max_count=self.max_traces_per_project
                )

        # Initialize LLM client
        llm = self._llm_client_factory(
            model=self.model, system_prompt=system_prompt, api_key=self.api_key
        )

        # Iteration-0 safeguard: prevent model from jumping to FINAL()
        # without exploring. Matches reference rlm/rlm/utils/prompts.py:136.
        first_user_msg = self.prompt_loader.render_iteration_zero(question=question)
        messages: list[dict[str, str]] = [
            {"role": "assistant", "content": context_metadata},
            {"role": "user", "content": first_user_msg},
        ]

        # Factory to create a callback with a frozen iteration value.
        # Without this, a closure over a mutable variable risks capturing
        # a stale iteration if the callback were ever invoked after the loop
        # advances (e.g., async execution, deferred calls).
        def _make_llm_callback(frozen_iteration: int) -> Callable[[str, str], str]:
            def llm_query_callback(instruction: str, content: str) -> str:
                return self._handle_llm_query(
                    instruction,
                    content,
                    trace,
                    token_usage,
                    frozen_iteration,
                    on_progress,
                    on_step=_write_step,
                    boundary=boundary,
                )

            return llm_query_callback

        # Acquire executor from pool or create standalone.
        # Capture pool in a local so the finally block is immune to
        # concurrent set_pool(None) from Shesha.stop().
        pool = self._pool
        if pool is not None:
            executor = pool.acquire()
            executor.llm_query_handler = _make_llm_callback(0)
            owns_executor = False
        else:
            executor = ContainerExecutor(llm_query_handler=_make_llm_callback(0))
            executor.start()
            owns_executor = True

        try:
            # Set up context in sandbox
            wrapped_documents = [wrap_untrusted(doc, boundary) for doc in documents]
            executor.setup_context(wrapped_documents)

            for iteration in range(self.max_iterations):
                # Check for cancellation before each iteration
                if cancel_event is not None and cancel_event.is_set():
                    answer = "[interrupted]"
                    query_result = QueryResult(
                        answer=answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                    )
                    _finalize_trace_and_cleanup(answer, "interrupted")
                    return query_result

                executor.llm_query_handler = _make_llm_callback(iteration)
                # Get LLM response
                response = llm.complete(messages=messages)
                token_usage.prompt_tokens += response.prompt_tokens
                token_usage.completion_tokens += response.completion_tokens

                step = trace.add_step(
                    type=StepType.CODE_GENERATED,
                    content=response.content,
                    iteration=iteration,
                    tokens_used=response.total_tokens,
                )
                _write_step(step)
                if on_progress:
                    on_progress(
                        StepType.CODE_GENERATED,
                        iteration,
                        response.content,
                        copy.copy(token_usage),
                    )

                # Extract code blocks first so they execute before bare FINAL
                # resolution. The LLM may define a variable in a code block
                # and then write bare FINAL(variable) in the same response;
                # the code block must run first so the variable exists in the
                # sandbox when we try to resolve it.
                code_blocks = extract_code_blocks(response.content)

                # Check for bare FINAL/FINAL_VAR in response text (outside code blocks).
                # The model sometimes outputs FINAL_VAR(x) as bare text without a
                # ```repl block. Matches reference rlm/rlm/core/rlm.py:240.
                bare_final = find_final_answer(response.content)

                if not code_blocks:
                    # No code blocks — handle bare FINAL or prompt for code
                    if bare_final is not None:
                        final_type, final_value = bare_final
                        if final_type == "final_var":
                            bare_answer = self._resolve_final_var(final_value, executor)
                            if bare_answer is None:
                                # Variable not found — retry instead of
                                # returning the variable name as the answer
                                messages.append({"role": "assistant", "content": response.content})
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            f"Variable '{final_value}' was not found in the "
                                            "REPL environment. Define it in a ```repl``` block "
                                            "first, then use FINAL_VAR(variable_name) to return it."
                                        ),
                                    }
                                )
                                continue
                        else:
                            bare_answer = final_value

                        step = trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=bare_answer,
                            iteration=iteration,
                        )
                        _write_step(step)
                        if on_progress:
                            on_progress(
                                StepType.FINAL_ANSWER,
                                iteration,
                                bare_answer,
                                copy.copy(token_usage),
                            )

                        query_result = QueryResult(
                            answer=bare_answer,
                            trace=trace,
                            token_usage=token_usage,
                            execution_time=time.time() - start_time,
                        )
                        _finalize_trace_and_cleanup(bare_answer, "success")
                        return query_result

                    # No bare FINAL either — prompt for code
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append(
                        {
                            "role": "user",
                            "content": self.prompt_loader.render_code_required(),
                        }
                    )
                    continue

                # Execute code blocks
                cb_result = self._execute_code_blocks(
                    code_blocks,
                    executor,
                    trace,
                    iteration,
                    token_usage,
                    on_progress,
                    _write_step,
                )
                final_answer = cb_result.final_answer

                # If code blocks didn't produce a final answer, check for
                # bare FINAL in the same response. Now that code blocks have
                # executed, any variables they defined exist in the sandbox.
                var_lookup_failed: str | None = cb_result.failed_final_var
                if final_answer is None and bare_final is not None:
                    final_type, final_value = bare_final
                    if final_type == "final_var":
                        resolved = self._resolve_final_var(final_value, executor)
                        if resolved is not None:
                            final_answer = resolved
                        else:
                            # Variable not found — record name so a helpful
                            # message is appended after the code-echo messages
                            var_lookup_failed = final_value
                    else:
                        final_answer = final_value

                    if final_answer is not None:
                        step = trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=final_answer,
                            iteration=iteration,
                        )
                        _write_step(step)
                        if on_progress:
                            on_progress(
                                StepType.FINAL_ANSWER,
                                iteration,
                                final_answer,
                                copy.copy(token_usage),
                            )

                if final_answer is not None:
                    verification, semantic_verification = self._run_verifications(
                        final_answer,
                        executor,
                        documents,
                        doc_names or [],
                        trace,
                        token_usage,
                        iteration,
                        on_progress,
                        _write_step,
                        boundary=boundary,
                    )

                    execution_time = time.time() - start_time
                    logger.info(
                        "Query completed in %.1fs (%d iters, %d+%d tokens)",
                        execution_time,
                        iteration + 1,
                        token_usage.prompt_tokens,
                        token_usage.completion_tokens,
                    )
                    query_result = QueryResult(
                        answer=final_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=execution_time,
                        verification=verification,
                        semantic_verification=semantic_verification,
                    )
                    _finalize_trace_and_cleanup(final_answer, "success")
                    return query_result

                # Recover from dead executor mid-loop
                if not executor.is_alive and pool is not None:
                    logger.warning("Executor died at iteration %d, recovering from pool", iteration)
                    executor.stop()
                    pool.discard(executor)
                    executor = pool.acquire()
                    executor.llm_query_handler = _make_llm_callback(iteration)
                    executor.setup_context(wrapped_documents)
                elif not executor.is_alive:
                    logger.error("Executor died at iteration %d with no pool, aborting", iteration)
                    answer = "[Executor died — cannot continue]"
                    query_result = QueryResult(
                        answer=answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                    )
                    _finalize_trace_and_cleanup(answer, "executor_died")
                    return query_result

                # Add assistant response, then per-block code echo messages
                messages.append({"role": "assistant", "content": response.content})
                for code_block, output, exec_result in zip(
                    code_blocks, cb_result.all_output, cb_result.exec_results
                ):
                    messages.append(
                        {
                            "role": "user",
                            "content": format_code_echo(
                                code_block, output, exec_result.vars, boundary=boundary
                            ),
                        }
                    )

                # Per-iteration continuation prompt re-instructs sub-LLM usage
                messages.append(
                    {
                        "role": "user",
                        "content": self.prompt_loader.render_iteration_continue(
                            question=question,
                        ),
                    }
                )

                if var_lookup_failed is not None:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Variable '{var_lookup_failed}' was not found in the "
                                "REPL environment. Define it in a ```repl``` block "
                                "first, then use FINAL_VAR(variable_name) to return it."
                            ),
                        }
                    )

            # Max iterations reached — ask LLM for one last answer
            fallback_messages = messages + [
                {
                    "role": "assistant",
                    "content": "Please provide a final answer to the user's question "
                    "based on the information provided.",
                }
            ]
            response = llm.complete(messages=fallback_messages)
            token_usage.prompt_tokens += response.prompt_tokens
            token_usage.completion_tokens += response.completion_tokens
            answer = response.content

            step = trace.add_step(
                type=StepType.FINAL_ANSWER,
                content=f"[max-iter fallback] {answer}",
                iteration=self.max_iterations - 1,
            )
            _write_step(step)

            query_result = QueryResult(
                answer=answer,
                trace=trace,
                token_usage=token_usage,
                execution_time=time.time() - start_time,
            )
            _finalize_trace_and_cleanup(answer, "max_iterations")
            return query_result

        finally:
            _finalize_trace_and_cleanup("[interrupted]", "interrupted")
            if owns_executor:
                executor.stop()
            else:
                # owns_executor is False only when pool was not None at acquire
                assert pool is not None
                executor.llm_query_handler = None
                try:
                    executor.reset_namespace()
                except Exception:
                    # Executor is broken (e.g., socket closed after protocol error).
                    # Stop it and discard from pool — don't return a broken executor.
                    executor.stop()
                    pool.discard(executor)
                else:
                    pool.release(executor)
