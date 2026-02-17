#!/usr/bin/env python3
"""OOLONG & OOLONG-Pairs benchmark using the paper's reference RLM.

Runs the same benchmarks as run_oolong_and_pairs.py but against the reference
RLM implementation in rlm/ instead of Shesha.  Outputs results in the same CSV
format for side-by-side comparison.

Environment variables:

  SHESHA_API_KEY        API key for the LLM provider (required).
  SHESHA_MODEL          LLM model (default: gpt-5.2, overridden by --model).
  MAX_WINDOWS_PER_LEN   Context windows per length (default: 1).
  REF_MAX_ITER          Max RLM iterations (default: 30).
  PLOT_ONLY             Set to 1 to regenerate plot from existing CSV.

Usage:

  python oolong/run_reference_implementation.py
  python oolong/run_reference_implementation.py --model openai/gpt-4o
  PLOT_ONLY=1 python oolong/run_reference_implementation.py
"""

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — sibling script + reference RLM package
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))  # for run_oolong_and_pairs
sys.path.insert(0, str(PROJECT_ROOT / "rlm"))  # for rlm package

import pandas as pd  # noqa: E402
from datasets import load_dataset  # noqa: E402
from run_oolong_and_pairs import (  # noqa: E402
    CACHE_PATH,
    CTX_LENS,
    _build_user_stats,
    _human_len,
    _parse_labeled_context,
    f1_score,
    make_pairs_tasks,
    parse_pairs_from_text,
    plot_results,
    score_oolong,
)

from rlm import RLM  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_PATH = SCRIPT_DIR / "oolong_ref_results.csv"
PLOT_PATH = SCRIPT_DIR / "oolong_ref_scaling.png"
LOG_PATH = SCRIPT_DIR / "ref-last-run.log"

BACKEND_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "azure": "azure_openai",
}

# Transient network errors worth retrying — collect what's importable.
_transient: list[type] = []
try:
    import httpx  # noqa: E402

    _transient.extend([httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError])
except ImportError:
    pass
try:
    import openai  # noqa: E402

    _transient.append(openai.APIConnectionError)
except ImportError:
    pass
_TRANSIENT_ERRORS: tuple[type, ...] = tuple(_transient)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger("oolong_ref")
log.addHandler(logging.NullHandler())


def _setup_logging() -> None:
    """Attach file and console handlers."""
    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.ERROR)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(ch)


def status(msg: str) -> None:
    """Print minimal progress to stdout and log it."""
    print(msg, flush=True)
    log.info(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OOLONG & OOLONG-Pairs benchmark using reference RLM.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model to use (overrides SHESHA_MODEL, default: gpt-5.2)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Accepted for CLI parity — no-op for reference RLM.",
    )
    return parser.parse_args()


def _parse_model(model_arg: str) -> tuple[str, str]:
    """Split LiteLLM-style 'provider/model' into (backend, model_name)."""
    if "/" in model_arg:
        backend, model_name = model_arg.split("/", 1)
    else:
        backend, model_name = "openai", model_arg
    backend = BACKEND_MAP.get(backend, backend)
    return backend, model_name


def _extract_total_tokens(usage_summary) -> int:
    """Sum input + output tokens across all models in a UsageSummary."""
    return sum(
        u.total_input_tokens + u.total_output_tokens
        for u in usage_summary.model_usage_summaries.values()
    )


_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0


def call_ref_rlm(
    question: str,
    context: str,
    rlm_instance: RLM,
) -> tuple[str, int]:
    """Run a reference RLM query with retry on transient network errors.

    Returns (answer_string, total_tokens).
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = rlm_instance.completion(prompt=context, root_prompt=question)
            answer = result.response
            if not isinstance(answer, str):
                log.debug(
                    "RLM returned non-string answer (%s), coercing: %r",
                    type(answer).__name__,
                    answer,
                )
                answer = str(answer)
            tokens = _extract_total_tokens(result.usage_summary)
            return answer, tokens
        except (_TRANSIENT_ERRORS) as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(
                "Transient error on attempt %d/%d, retrying in %.0fs: %s",
                attempt + 1,
                _MAX_RETRIES,
                delay,
                exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _setup_logging()
    args = _parse_args()

    # Re-plot only mode
    if os.getenv("PLOT_ONLY") == "1":
        if CSV_PATH.exists():
            plot_results(CSV_PATH, PLOT_PATH)
            status(f"Wrote {PLOT_PATH}")
        else:
            status(f"No CSV found at {CSV_PATH}")
        return

    t_start = time.monotonic()
    model = args.model or os.getenv("SHESHA_MODEL", "gpt-5.2")
    max_win = int(os.getenv("MAX_WINDOWS_PER_LEN", "1"))
    max_iter = int(os.getenv("REF_MAX_ITER", "30"))

    backend, model_name = _parse_model(model)
    log.info("=== Reference RLM Benchmark Run ===")
    log.info(
        "backend=%s  model=%s  max_windows=%d  max_iter=%d",
        backend,
        model_name,
        max_win,
        max_iter,
    )
    status(f"backend={backend}  model={model_name}")
    status(f"max_windows={max_win}  max_iter={max_iter}")

    # --- Reference RLM setup ---
    api_key = os.getenv("SHESHA_API_KEY")
    if not api_key:
        print("Error: SHESHA_API_KEY environment variable not set.")
        sys.exit(1)
    ref = RLM(
        backend=backend,
        backend_kwargs={"api_key": api_key, "model_name": model_name},
        environment="local",
        max_iterations=max_iter,
    )
    log.info("Reference RLM initialized")

    # --- Load dataset (cached locally after first fetch) ---
    if CACHE_PATH.exists():
        status("Loading cached trec_coarse data...")
        trec = pd.read_parquet(CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]
        log.info("Loaded from cache: %s (%d rows)", CACHE_PATH, len(trec))
    else:
        status("Fetching oolongbench/oolong-synth (first run, will cache)...")
        ds = load_dataset("oolongbench/oolong-synth")
        df = pd.DataFrame(ds["validation"])
        trec = df[df["dataset"].str.contains("trec", case=False, na=False)].copy()
        trec.to_parquet(CACHE_PATH)
        log.info("Cached %d trec_coarse rows to %s", len(trec), CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]

    log.info("trec_coarse rows after length filter: %d", len(trec))
    log.info("Context lengths present: %s", sorted(trec["context_len"].unique()))
    status(f"Loaded {len(trec)} trec_coarse rows, {trec['context_len'].nunique()} context lengths")

    if trec.empty:
        status("ERROR: no trec_coarse rows found")
        return

    # --- Group by context window ---
    groups = list(trec.groupby(["context_len", "context_window_id"]))
    by_len: dict[int, list] = {}
    for (ctx_len, ctx_id), g in groups:
        by_len.setdefault(ctx_len, []).append((ctx_id, g))

    results: list[dict] = []

    # --- Count total steps for progress reporting ---
    total_steps = 0
    for ctx_len in CTX_LENS:
        windows = by_len.get(ctx_len, [])[:max_win]
        for _, g in windows:
            total_steps += len(g)  # oolong questions
            total_steps += 20  # pairs tasks per window
    step = 0
    step_times: list[float] = []
    cumulative_scores: list[float] = []
    cumulative_tokens: int = 0

    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(n)

    def _progress(
        label: str,
        ctx: str,
        score: float,
        dur: float,
        tokens: int = 0,
    ) -> None:
        nonlocal step, cumulative_tokens
        step += 1
        step_times.append(dur)
        cumulative_tokens += tokens
        avg = sum(step_times) / len(step_times)
        eta_s = avg * (total_steps - step)
        eta_m, eta_sec = divmod(int(eta_s), 60)
        eta_h, eta_m = divmod(eta_m, 60)
        ts = datetime.now().strftime("%H:%M:%S")
        eta_str = f"{eta_h}h{eta_m:02d}m" if eta_h else f"{eta_m}m{eta_sec:02d}s"

        if "ool" in label:
            cumulative_scores.append(score)
        n_scored = len(cumulative_scores)
        if n_scored > 0:
            pct = 100 * sum(cumulative_scores) / n_scored
            acc_str = f"acc={pct:.0f}%({n_scored})"
        else:
            acc_str = ""

        tok_str = f"tok={_fmt_tokens(cumulative_tokens)}" if cumulative_tokens else ""

        print(
            f"  [{ts}] {step}/{total_steps}  {ctx}  {label}  "
            f"score={score:.2f}  ({dur:.0f}s)  "
            f"{acc_str}  {tok_str}  ETA {eta_str}",
            flush=True,
        )

    status(f"Total steps: {total_steps}")

    try:
        for ctx_len in CTX_LENS:
            windows = by_len.get(ctx_len, [])
            if not windows:
                continue
            windows = windows[:max_win]
            hl = _human_len(ctx_len)

            for w_idx, (ctx_id, g) in enumerate(windows, 1):
                t_win = time.monotonic()
                n_oolong = len(g)
                log.info(
                    "--- %s window %d/%d (id=%s, %d oolong questions) ---",
                    hl,
                    w_idx,
                    len(windows),
                    ctx_id,
                    n_oolong,
                )

                context = g["context_window_text"].iloc[0]
                context_labeled = g["context_window_text_with_labels"].iloc[0]

                # --- OOLONG ---
                ool_scores: list[float] = []

                for _, row in g.iterrows():
                    t_q = time.monotonic()
                    try:
                        pred, toks = call_ref_rlm(
                            row["question"],
                            context,
                            ref,
                        )
                        s = score_oolong(pred, row["answer"])
                        ool_scores.append(s)
                        results.append(
                            {
                                "benchmark": "oolong",
                                "model": f"ref:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": row["id"],
                                "score": s,
                            }
                        )
                        _progress("ref:ool", hl, s, time.monotonic() - t_q, toks)
                        log.debug(
                            "oolong ref id=%s score=%.1f gold=%r pred=%r",
                            row["id"],
                            s,
                            row["answer"],
                            pred[:200],
                        )
                    except Exception:
                        _progress("ref:ool", hl, 0.0, time.monotonic() - t_q)
                        log.error(
                            "oolong ref id=%s FAILED:\n%s",
                            row["id"],
                            traceback.format_exc(),
                        )

                # --- OOLONG-PAIRS ---
                entries = _parse_labeled_context(context_labeled)
                user_stats = _build_user_stats(entries)
                log.info(
                    "Labeled context: %d entries, %d users",
                    len(entries),
                    len(user_stats),
                )
                pairs_tasks = make_pairs_tasks(user_stats)

                pairs_scores: list[float] = []

                for t_idx, (qtext, gold_pairs) in enumerate(pairs_tasks, 1):
                    t_q = time.monotonic()
                    try:
                        pred, toks = call_ref_rlm(qtext, context, ref)
                        pred_pairs = parse_pairs_from_text(pred)
                        s = f1_score(pred_pairs, gold_pairs)
                        pairs_scores.append(s)
                        results.append(
                            {
                                "benchmark": "oolong_pairs",
                                "model": f"ref:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": f"pairs_{t_idx}",
                                "score": s,
                            }
                        )
                        _progress(
                            "ref:pairs",
                            hl,
                            s,
                            time.monotonic() - t_q,
                            toks,
                        )
                        log.debug(
                            "pairs ref t=%d f1=%.3f |pred|=%d |gold|=%d",
                            t_idx,
                            s,
                            len(pred_pairs),
                            len(gold_pairs),
                        )
                    except Exception:
                        _progress("ref:pairs", hl, 0.0, time.monotonic() - t_q)
                        log.error(
                            "pairs ref t=%d FAILED:\n%s",
                            t_idx,
                            traceback.format_exc(),
                        )

                # --- Per-window status line ---
                elapsed = time.monotonic() - t_win
                parts = [f"  {hl:>4s} [{w_idx}/{len(windows)}]"]
                if ool_scores:
                    avg = 100 * sum(ool_scores) / len(ool_scores)
                    parts.append(f"ref:ool={avg:.0f}%")
                if pairs_scores:
                    avg = 100 * sum(pairs_scores) / len(pairs_scores)
                    parts.append(f"ref:pairs={avg:.0f}%")
                parts.append(f"({elapsed:.0f}s)")
                status("  ".join(parts))

    except KeyboardInterrupt:
        status("\nInterrupted — saving partial results")

    # --- Save & plot ---
    if results:
        out = pd.DataFrame(results)
        out.to_csv(CSV_PATH, index=False)
        status(f"Wrote {CSV_PATH} ({len(out)} rows)")

        try:
            plot_results(CSV_PATH, PLOT_PATH)
            status(f"Wrote {PLOT_PATH}")
        except Exception:
            log.error("Plotting failed:\n%s", traceback.format_exc())
    else:
        status("No results collected")

    elapsed_total = time.monotonic() - t_start
    status(f"Done in {elapsed_total:.0f}s  log: {LOG_PATH}")


if __name__ == "__main__":
    main()
