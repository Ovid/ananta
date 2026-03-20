#!/usr/bin/env python3
"""OOLONG & OOLONG-Pairs benchmark for Ananta RLM.

Reproduces the OOLONG and OOLONG-Pairs evaluations from the Recursive Language
Models paper (arXiv:2512.24601).  Uses the trec_coarse split of the
oolongbench/oolong-synth HuggingFace dataset (validation split).

OOLONG:       Exact-match accuracy on question-answering over long contexts.
OOLONG-Pairs: Set-F1 over 20 user-ID pair-finding tasks (Appendix E.1).

Two evaluation modes are supported and can be enabled independently:

  "base"  — single-shot: the full context + question is sent to the LLM in one
            call via LiteLLM.  Tests the model's raw long-context ability.
  "rlm"   — Ananta RLM: the context is uploaded as a document and the RLM loop
            explores it programmatically before answering.  Tests whether the
            recursive approach outperforms raw context.

Outputs (all written to the oolong/ directory):
  oolong_results.csv    — one row per (benchmark, model, context_len, task)
  oolong_scaling.png    — score-vs-context-length plot (log₂ x-axis)
  last-run.log          — full debug log (predictions, gold answers, errors)

Environment variables:

  Required
  ────────
  ANANTA_API_KEY        API key passed to Ananta / LiteLLM.

  Model
  ─────
  ANANTA_MODEL          LLM to use for both base and RLM modes.
                        Default: gpt-5.2

  Evaluation scope
  ────────────────
  RUN_BASE              Set to 1 to enable the base-model (single-shot) runs.
                        Default: 0  (off — only RLM runs by default)
  RUN_RLM               Set to 1 to enable Ananta RLM runs.
                        Default: 1
  MAX_WINDOWS_PER_LEN   How many context windows to evaluate per context length.
                        Lower = faster / cheaper.  The dataset has ~50 windows
                        per length; set higher for more statistical power.
                        Default: 1

  Ananta tuning
  ─────────────
  ANANTA_STORAGE        Directory for Ananta's project storage.
                        Default: ./ananta_data
  ANANTA_MAX_ITER       Maximum RLM loop iterations before forced stop.
                        Increase if the model is truncated mid-reasoning.
                        Default: 40

  Convenience
  ───────────
  PLOT_ONLY             Set to 1 to skip evaluation entirely and regenerate
                        the plot from an existing oolong_results.csv.

  CLI arguments
  ─────────────
  --model MODEL         LLM to use (overrides ANANTA_MODEL env var).

Usage examples:

  # Minimal RLM-only run (one window per length, cheapest)
  export ANANTA_API_KEY="sk-..."
  python oolong/run_oolong_and_pairs.py

  # Use a specific model via CLI flag
  python oolong/run_oolong_and_pairs.py --model gpt-4o

  # Compare base vs RLM with more statistical power
  export ANANTA_API_KEY="sk-..."
  export RUN_BASE=1
  export MAX_WINDOWS_PER_LEN=5
  python oolong/run_oolong_and_pairs.py

  # Re-plot after a previous run
  PLOT_ONLY=1 python oolong/run_oolong_and_pairs.py

Note: if this is your first time running on the Docker container, it will
appear to hang for ten or fifteen minutes while it's downloading.
"""

import argparse
import ast
import itertools
import logging
import os
import re
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import UnraisableHookArgs

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 — must follow matplotlib.use()
import pandas as pd  # noqa: E402
from datasets import load_dataset  # noqa: E402
from dateutil import parser as dateparser  # noqa: E402
from litellm import completion  # noqa: E402

from ananta import Ananta, AnantaConfig  # noqa: E402
from ananta.exceptions import ProjectExistsError  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABELS = [
    "description and abstract concept",
    "entity",
    "human being",
    "numeric value",
    "location",
    "abbreviation",
]

CTX_LENS = [8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_PATH = SCRIPT_DIR / "last-run.log"
CSV_PATH = SCRIPT_DIR / "oolong_results.csv"
PLOT_PATH = SCRIPT_DIR / "oolong_scaling.png"
CACHE_PATH = SCRIPT_DIR / "trec_coarse.parquet"

# ---------------------------------------------------------------------------
# Logging — handlers are attached in _setup_logging(), called from main(),
# so that importing scoring helpers doesn't truncate the log file.
# ---------------------------------------------------------------------------

log = logging.getLogger("oolong")
log.addHandler(logging.NullHandler())


def _setup_logging() -> None:
    """Attach file and console handlers. Called once from main()."""
    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.ERROR)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(ch)


def _human_len(n: int) -> str:
    if n >= 1_048_576:
        return f"{n // 1_048_576}M"
    return f"{n // 1024}K"


def status(msg: str) -> None:
    """Print minimal progress to stdout and log it."""
    print(msg, flush=True)
    log.info(msg)


# ---------------------------------------------------------------------------
# Scoring: OOLONG (exact match)
# ---------------------------------------------------------------------------


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _parse_gold_answers(gold_str: str) -> list[str]:
    gold_str = gold_str.strip()
    try:
        v = ast.literal_eval(gold_str)
        if isinstance(v, list):
            return [_normalize_ws(str(x)).lower() for x in v]
    except Exception:
        pass  # gold is a plain string, not a Python literal
    return [_normalize_ws(gold_str).lower()]


def _extract_candidate(pred: str) -> str:
    lines = [ln.strip() for ln in pred.splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    last = re.sub(
        r"^(final answer|answer|label|user)\s*:\s*", "", last, flags=re.I
    ).strip()
    return _normalize_ws(last)


def score_oolong(pred: str, gold_str: str) -> float:
    golds = _parse_gold_answers(gold_str)
    cand = _extract_candidate(pred).lower()

    # Try list-style parse of prediction
    if "[" in pred and "]" in pred:
        try:
            v = ast.literal_eval(pred[pred.find("[") : pred.rfind("]") + 1])
            if isinstance(v, list) and len(v) > 0:
                cand_list = [_normalize_ws(str(x)).lower() for x in v]
                if len(cand_list) == 1 and cand_list[0] in golds:
                    return 1.0
        except Exception:
            pass  # prediction isn't a valid Python list

    if cand in golds:
        return 1.0

    # Substring match for comparison phrases embedded in full-sentence answers.
    # OOLONG questions request "Answer: X is [relation] Y" but gold is just [relation].
    # Skip numeric golds — they must fall through to the numeric decay scorer.
    for g in golds:
        if not g.lstrip("-").isdigit() and g in cand:
            return 1.0

    # Numerical scoring: 0.75^|y - ŷ| per Bertsch et al. (2025) / arXiv:2512.24601.
    if len(golds) == 1:
        try:
            gold_num = int(golds[0])
            pred_num = int(float(cand))
            return 0.75 ** abs(gold_num - pred_num)
        except ValueError:
            pass  # Not numeric — fall through to token-set and final 0.0

    # Token-set fallback for single-atom golds
    def toks(s: str) -> list[str]:
        return [t.strip().lower() for t in re.split(r"[,\s]+", s) if t.strip()]

    if (
        len(golds) == 1
        and not (golds[0].startswith("[") and golds[0].endswith("]"))
    ):
        if toks(cand) == toks(golds[0]):
            return 1.0

    return 0.0


# ---------------------------------------------------------------------------
# Scoring: OOLONG-Pairs (set F1)
# ---------------------------------------------------------------------------


def parse_pairs_from_text(text: str) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for line in text.splitlines():
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)  # strip list prefixes
        nums = re.findall(r"\d+", line)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a == b:
                continue
            lo, hi = (a, b) if a < b else (b, a)
            pairs.add((lo, hi))
    return pairs


def f1_score(
    pred_pairs: set[tuple[int, int]], gold_pairs: set[tuple[int, int]]
) -> float:
    if not pred_pairs and not gold_pairs:
        return 1.0
    if not pred_pairs or not gold_pairs:
        return 0.0
    tp = len(pred_pairs & gold_pairs)
    prec = tp / len(pred_pairs)
    rec = tp / len(gold_pairs)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


# ---------------------------------------------------------------------------
# Gold-pair generation from labeled context (Appendix E.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    user_id: int
    date: datetime
    label: str


def _parse_labeled_context(text: str) -> list[_Entry]:
    entries: list[_Entry] = []
    for line in text.splitlines():
        if "Date:" not in line or "User:" not in line or "Label:" not in line:
            continue
        m = re.search(
            r"Date:\s*(.*?)\s*\|\|\s*User:\s*(\d+).*?\|\|\s*Label:\s*([^\|]+)\s*$",
            line,
        )
        if not m:
            continue
        try:
            dt = dateparser.parse(m.group(1))
        except Exception:
            continue
        entries.append(
            _Entry(
                user_id=int(m.group(2)),
                date=dt,
                label=_normalize_ws(m.group(3)).lower(),
            )
        )
    if not entries and len(text.strip()) > 0:
        raise ValueError(
            "Parsed 0 entries from non-empty labeled context — "
            "dataset format may have changed"
        )
    return entries


def _build_user_stats(
    entries: list[_Entry],
) -> dict[int, dict[str, list[datetime]]]:
    stats: dict[int, dict[str, list[datetime]]] = {}
    for e in entries:
        stats.setdefault(e.user_id, {}).setdefault(e.label, []).append(e.date)
    return stats


def _has_any(su: dict[str, list[datetime]], labels: set[str]) -> bool:
    return any(lab in su and len(su[lab]) > 0 for lab in labels)


def _all_after(
    su: dict[str, list[datetime]], label: str, cutoff: datetime
) -> bool:
    return label not in su or all(d > cutoff for d in su[label])


def _all_before(
    su: dict[str, list[datetime]], label: str, cutoff: datetime
) -> bool:
    return label not in su or all(d < cutoff for d in su[label])


def _count(su: dict[str, list[datetime]], label: str) -> int:
    return len(su.get(label, []))


def _all_combos(ids: list[int]) -> set[tuple[int, int]]:
    return set(itertools.combinations(sorted(ids), 2))


def _cross(a: set[int], b: set[int]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for x in a:
        for y in b:
            if x != y:
                lo, hi = (x, y) if x < y else (y, x)
                out.add((lo, hi))
    return out


def make_pairs_tasks(
    user_stats: dict[int, dict[str, list[datetime]]],
) -> list[tuple[str, set[tuple[int, int]]]]:
    """Generate 20 OOLONG-Pairs tasks with gold answers (per Appendix E.1)."""
    users = list(user_stats.keys())
    NUM, LOC, ENT, HUM = "numeric value", "location", "entity", "human being"
    DESC, ABBR = "description and abstract concept", "abbreviation"

    def elig(labels: set[str]) -> set[int]:
        return {u for u in users if _has_any(user_stats[u], labels)}

    def filt(pred) -> set[int]:
        return {u for u in users if pred(u)}

    c4 = dateparser.parse("Jan 6, 2023")
    c5 = dateparser.parse("Mar 15, 2023")
    c7 = dateparser.parse("Feb 1, 2023")
    c9 = dateparser.parse("Apr 10, 2023")
    c10 = dateparser.parse("May 20, 2023")

    intro = (
        "Using the dataset above: each instance's question belongs to exactly "
        "one of these semantic labels (not shown in the data): "
        f"{', '.join(LABELS)}. "
        "Return pairs of user IDs (unique pairs; smaller ID first)."
    )

    tasks: list[tuple[str, set[tuple[int, int]]]] = []

    # Tasks 1-10: combination tasks
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " NUMERIC-VALUE or LOCATION instance.",
        _all_combos(sorted(elig({NUM, LOC}))),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " ENTITY or HUMAN-BEING instance.",
        _all_combos(sorted(elig({ENT, HUM}))),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " DESCRIPTION/ABSTRACT or ABBREVIATION instance.",
        _all_combos(sorted(elig({DESC, ABBR}))),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " HUMAN-BEING or LOCATION instance, and for each user, every"
        " HUMAN-BEING instance is dated after 2023-01-06.",
        _all_combos(sorted({
            u for u in users
            if _has_any(user_stats[u], {HUM, LOC})
            and _all_after(user_stats[u], HUM, c4)
        })),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " ENTITY or NUMERIC-VALUE instance, and for each user, every ENTITY"
        " instance is dated before 2023-03-15.",
        _all_combos(sorted({
            u for u in users
            if _has_any(user_stats[u], {ENT, NUM})
            and _all_before(user_stats[u], ENT, c5)
        })),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " of: ENTITY, ABBREVIATION, LOCATION.",
        _all_combos(sorted(elig({ENT, ABBR, LOC}))),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " DESCRIPTION/ABSTRACT or NUMERIC-VALUE instance, and for each user,"
        " every NUMERIC-VALUE instance is dated after 2023-02-01.",
        _all_combos(sorted({
            u for u in users
            if _has_any(user_stats[u], {DESC, NUM})
            and _all_after(user_stats[u], NUM, c7)
        })),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " of: HUMAN-BEING, NUMERIC-VALUE, LOCATION.",
        _all_combos(sorted(elig({HUM, NUM, LOC}))),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " ENTITY or LOCATION instance, and for each user, every LOCATION"
        " instance is dated after 2023-04-10.",
        _all_combos(sorted({
            u for u in users
            if _has_any(user_stats[u], {ENT, LOC})
            and _all_after(user_stats[u], LOC, c9)
        })),
    ))
    tasks.append((
        intro + " Find all user-id pairs where BOTH users have at least one"
        " NUMERIC-VALUE or ABBREVIATION instance, and for each user, every"
        " ABBREVIATION instance is dated before 2023-05-20.",
        _all_combos(sorted({
            u for u in users
            if _has_any(user_stats[u], {NUM, ABBR})
            and _all_before(user_stats[u], ABBR, c10)
        })),
    ))

    # Tasks 11-20: cross-product tasks
    tasks.append((
        intro + " Find all pairs where one user has >=1 ENTITY and >=1"
        " ABBREVIATION, and the other user has exactly 1 ENTITY.",
        _cross(
            filt(lambda u: _count(user_stats[u], ENT) >= 1
                 and _count(user_stats[u], ABBR) >= 1),
            filt(lambda u: _count(user_stats[u], ENT) == 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=2 NUMERIC-VALUE"
        " instances, and the other user has >=1 LOCATION and >=1 HUMAN-BEING.",
        _cross(
            filt(lambda u: _count(user_stats[u], NUM) >= 2),
            filt(lambda u: _count(user_stats[u], LOC) >= 1
                 and _count(user_stats[u], HUM) >= 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has exactly 1"
        " DESCRIPTION/ABSTRACT, and the other has >=1 ABBREVIATION and >=1"
        " ENTITY.",
        _cross(
            filt(lambda u: _count(user_stats[u], DESC) == 1),
            filt(lambda u: _count(user_stats[u], ABBR) >= 1
                 and _count(user_stats[u], ENT) >= 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=1 HUMAN-BEING and >=1"
        " NUMERIC-VALUE, and the other has exactly 2 LOCATION instances.",
        _cross(
            filt(lambda u: _count(user_stats[u], HUM) >= 1
                 and _count(user_stats[u], NUM) >= 1),
            filt(lambda u: _count(user_stats[u], LOC) == 2),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=1 ENTITY, >=1 LOCATION,"
        " and >=1 ABBREVIATION, and the other has exactly 1 NUMERIC-VALUE.",
        _cross(
            filt(lambda u: _count(user_stats[u], ENT) >= 1
                 and _count(user_stats[u], LOC) >= 1
                 and _count(user_stats[u], ABBR) >= 1),
            filt(lambda u: _count(user_stats[u], NUM) == 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=1 DESCRIPTION/ABSTRACT"
        " and >=1 HUMAN-BEING, and the other has >=2 ENTITY and exactly 1"
        " ABBREVIATION.",
        _cross(
            filt(lambda u: _count(user_stats[u], DESC) >= 1
                 and _count(user_stats[u], HUM) >= 1),
            filt(lambda u: _count(user_stats[u], ENT) >= 2
                 and _count(user_stats[u], ABBR) == 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has exactly 1 NUMERIC-VALUE,"
        " and the other has >=1 LOCATION and >=1 DESCRIPTION/ABSTRACT.",
        _cross(
            filt(lambda u: _count(user_stats[u], NUM) == 1),
            filt(lambda u: _count(user_stats[u], LOC) >= 1
                 and _count(user_stats[u], DESC) >= 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=1 ABBREVIATION and"
        " exactly 1 HUMAN-BEING, and the other has >=1 ENTITY and >=1"
        " NUMERIC-VALUE.",
        _cross(
            filt(lambda u: _count(user_stats[u], ABBR) >= 1
                 and _count(user_stats[u], HUM) == 1),
            filt(lambda u: _count(user_stats[u], ENT) >= 1
                 and _count(user_stats[u], NUM) >= 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=2 LOCATION and >=1"
        " ENTITY, and the other has exactly 1 DESCRIPTION/ABSTRACT and"
        " exactly 1 ABBREVIATION.",
        _cross(
            filt(lambda u: _count(user_stats[u], LOC) >= 2
                 and _count(user_stats[u], ENT) >= 1),
            filt(lambda u: _count(user_stats[u], DESC) == 1
                 and _count(user_stats[u], ABBR) == 1),
        ),
    ))
    tasks.append((
        intro + " Find all pairs where one user has >=1 NUMERIC-VALUE and >=1"
        " HUMAN-BEING, and the other has >=1 LOCATION, >=1 ENTITY, and"
        " exactly 1 ABBREVIATION.",
        _cross(
            filt(lambda u: _count(user_stats[u], NUM) >= 1
                 and _count(user_stats[u], HUM) >= 1),
            filt(lambda u: _count(user_stats[u], LOC) >= 1
                 and _count(user_stats[u], ENT) >= 1
                 and _count(user_stats[u], ABBR) == 1),
        ),
    ))

    return tasks


# ---------------------------------------------------------------------------
# Model callers
# ---------------------------------------------------------------------------


def call_base(prompt: str, model: str) -> tuple[str, int]:
    """Run a single-shot base model call. Returns (answer_string, total_tokens_used)."""
    resp = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    tokens = resp.get("usage", {}).get("total_tokens", 0) or 0
    return resp["choices"][0]["message"]["content"], tokens


def call_rlm(question: str, project) -> tuple[str, int]:
    """Run an RLM query. Returns (answer_string, total_tokens_used)."""
    result = project.query(question)
    # The sandbox FINAL() accepts any type; coerce to str for scoring.
    answer = result.answer
    if not isinstance(answer, str):
        log.debug(
            "RLM returned non-string answer (%s), coercing: %r",
            type(answer).__name__, answer,
        )
        answer = str(answer)
    return answer, result.token_usage.total_tokens


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_results(csv_path: Path, plot_path: Path) -> None:
    df = pd.read_csv(csv_path)
    agg = (
        df.groupby(["benchmark", "model", "context_len"])["score"]
        .mean()
        .reset_index()
    )
    benchmarks = [
        b for b in ["oolong", "oolong_pairs"] if b in agg["benchmark"].values
    ]
    if not benchmarks:
        log.warning("No results to plot")
        return

    fig, axes = plt.subplots(len(benchmarks), 1, figsize=(8, 4.5 * len(benchmarks)))
    if len(benchmarks) == 1:
        axes = [axes]

    titles = {"oolong": "OOLONG (trec_coarse)", "oolong_pairs": "OOLONG-Pairs"}
    for ax, bench in zip(axes, benchmarks):
        sub = agg[agg["benchmark"] == bench]
        for model in sorted(sub["model"].unique()):
            s = sub[sub["model"] == model].sort_values("context_len")
            ax.plot(s["context_len"], 100 * s["score"], marker="o", label=model)
        ax.set_xscale("log", base=2)
        ax.set_ylim(0, 100)
        ax.set_title(titles.get(bench, bench))
        ax.set_xlabel("Context Length (tokens, log scale)")
        ax.set_ylabel("Score (%)")
        ax.legend()

    plt.tight_layout()
    plt.savefig(plot_path, dpi=200)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OOLONG & OOLONG-Pairs benchmark for Ananta RLM.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model to use (overrides ANANTA_MODEL env var, default: gpt-5.2)",
    )
    return parser.parse_args()


def _install_urllib3_cleanup_hook() -> None:
    """Suppress harmless urllib3 shutdown errors on Python 3.14+.

    During GC, HTTP response finalizers may run after file handles close,
    producing "ValueError: I/O operation on closed file". This is harmless.
    """
    original_hook = sys.unraisablehook

    def suppress_urllib3_error(unraisable: "UnraisableHookArgs") -> None:
        if unraisable.exc_type is ValueError and "I/O operation on closed file" in str(
            unraisable.exc_value
        ):
            return
        original_hook(unraisable)

    sys.unraisablehook = suppress_urllib3_error


def main() -> None:
    _setup_logging()
    _install_urllib3_cleanup_hook()
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
    model = args.model or os.getenv("ANANTA_MODEL", "gpt-5.2")
    run_base = os.getenv("RUN_BASE", "0") == "1"
    run_rlm = os.getenv("RUN_RLM", "1") == "1"
    max_win = int(os.getenv("MAX_WINDOWS_PER_LEN", "1"))

    log.info("=== OOLONG Benchmark Run ===")
    log.info(
        "model=%s  run_base=%s  run_rlm=%s  max_windows=%d",
        model, run_base, run_rlm, max_win,
    )

    # Log provider and model (LiteLLM format: "provider/model" or just "model")
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        provider, model_name = "openai", model
    status(f"provider={provider}  model={model_name}")

    modes = []
    if run_base:
        modes.append("base")
    if run_rlm:
        modes.append("rlm")
    status(f"modes={'+'.join(modes)}  max_windows={max_win}")

    if not modes:
        status("Nothing to run (RUN_BASE=0 and RUN_RLM=0)")
        return

    # --- Ananta setup ---
    sh = None
    if run_rlm:
        cfg = AnantaConfig(
            model=model,
            api_key=os.getenv("ANANTA_API_KEY"),
            storage_path=os.getenv("ANANTA_STORAGE", "./ananta_data"),
            max_iterations=int(os.getenv("ANANTA_MAX_ITER", "30")),
        )
        sh = Ananta(config=cfg)
        log.info("Ananta initialized: %s", cfg)

    # --- Load dataset (cached locally after first fetch) ---
    if CACHE_PATH.exists():
        status("Loading cached trec_coarse data...")
        trec = pd.read_parquet(CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]
        log.info("Loaded from cache: %s (%d rows)", CACHE_PATH, len(trec))
    else:
        status("Fetching oolongbench/oolong-synth (first run, will cache)...")
        ds = load_dataset("oolongbench/oolong-synth")
        df = pd.DataFrame(ds["validation"])  # trec_coarse is in the validation split
        trec = df[df["dataset"].str.contains("trec", case=False, na=False)].copy()
        trec.to_parquet(CACHE_PATH)
        log.info("Cached %d trec_coarse rows to %s", len(trec), CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]

    log.info(
        "trec_coarse rows after length filter: %d", len(trec),
    )
    log.info("Context lengths present: %s", sorted(trec["context_len"].unique()))
    status(
        f"Loaded {len(trec)} trec_coarse rows, "
        f"{trec['context_len'].nunique()} context lengths"
    )

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
    n_modes = int(run_base) + int(run_rlm)
    total_steps = 0
    for ctx_len in CTX_LENS:
        windows = by_len.get(ctx_len, [])[:max_win]
        for _, g in windows:
            total_steps += len(g) * n_modes  # oolong questions
            total_steps += 20 * n_modes       # pairs tasks per window
    step = 0
    step_times: list[float] = []  # durations for ETA
    cumulative_scores: list[float] = []  # running oolong scores for success rate
    cumulative_tokens: int = 0  # running total tokens

    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(n)

    def _progress(
        label: str, ctx: str, score: float, dur: float, tokens: int = 0,
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

        # Running success rate for oolong questions only
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

    status(f"Total steps: {total_steps} ({total_steps // n_modes} queries x {n_modes} mode(s))")

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
                    hl, w_idx, len(windows), ctx_id, n_oolong,
                )

                context = g["context_window_text"].iloc[0]
                context_labeled = g["context_window_text_with_labels"].iloc[0]

                # One Ananta project per context window (queries are independent)
                rlm_project = None
                if run_rlm and sh is not None:
                    proj_name = f"oolong_{ctx_len}_{ctx_id}"
                    try:
                        rlm_project = sh.create_project(proj_name)
                    except ProjectExistsError:
                        sh.delete_project(proj_name)
                        rlm_project = sh.create_project(proj_name)
                        log.debug("Replaced existing project '%s'", proj_name)
                    with tempfile.TemporaryDirectory() as td:
                        fpath = os.path.join(td, "context.txt")
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write(context)
                        rlm_project.upload(fpath)
                    log.info(
                        "Ananta project '%s' created (%d chars)",
                        proj_name, len(context),
                    )

                # --- OOLONG ---
                ool_base: list[float] = []
                ool_rlm: list[float] = []

                for _, row in g.iterrows():
                    prompt = context + "\n\n" + row["question"]

                    if run_base:
                        t_q = time.monotonic()
                        try:
                            pred, toks = call_base(prompt, model)
                            s = score_oolong(pred, row["answer"])
                            ool_base.append(s)
                            results.append({
                                "benchmark": "oolong",
                                "model": f"base:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": row["id"],
                                "score": s,
                            })
                            _progress("base:ool", hl, s, time.monotonic() - t_q, toks)
                            log.debug(
                                "oolong base id=%s score=%.1f gold=%r pred=%r",
                                row["id"], s, row["answer"], pred[:200],
                            )
                        except Exception:
                            _progress("base:ool", hl, 0.0, time.monotonic() - t_q)
                            log.error(
                                "oolong base id=%s FAILED:\n%s",
                                row["id"], traceback.format_exc(),
                            )

                    if run_rlm and rlm_project is not None:
                        t_q = time.monotonic()
                        try:
                            pred, toks = call_rlm(row["question"], rlm_project)
                            s = score_oolong(pred, row["answer"])
                            ool_rlm.append(s)
                            results.append({
                                "benchmark": "oolong",
                                "model": f"rlm:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": row["id"],
                                "score": s,
                            })
                            _progress("rlm:ool", hl, s, time.monotonic() - t_q, toks)
                            log.debug(
                                "oolong rlm id=%s score=%.1f gold=%r pred=%r",
                                row["id"], s, row["answer"], pred[:200],
                            )
                        except Exception:
                            _progress("rlm:ool", hl, 0.0, time.monotonic() - t_q)
                            log.error(
                                "oolong rlm id=%s FAILED:\n%s",
                                row["id"], traceback.format_exc(),
                            )

                # --- OOLONG-PAIRS ---
                entries = _parse_labeled_context(context_labeled)
                user_stats = _build_user_stats(entries)
                log.info(
                    "Labeled context: %d entries, %d users", len(entries), len(user_stats),
                )
                pairs_tasks = make_pairs_tasks(user_stats)

                pairs_base: list[float] = []
                pairs_rlm: list[float] = []

                for t_idx, (qtext, gold_pairs) in enumerate(pairs_tasks, 1):
                    prompt = context + "\n\n" + qtext

                    if run_base:
                        t_q = time.monotonic()
                        try:
                            pred, toks = call_base(prompt, model)
                            pred_pairs = parse_pairs_from_text(pred)
                            s = f1_score(pred_pairs, gold_pairs)
                            pairs_base.append(s)
                            results.append({
                                "benchmark": "oolong_pairs",
                                "model": f"base:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": f"pairs_{t_idx}",
                                "score": s,
                            })
                            _progress("base:pairs", hl, s, time.monotonic() - t_q, toks)
                            log.debug(
                                "pairs base t=%d f1=%.3f |pred|=%d |gold|=%d",
                                t_idx, s, len(pred_pairs), len(gold_pairs),
                            )
                        except Exception:
                            _progress("base:pairs", hl, 0.0, time.monotonic() - t_q)
                            log.error(
                                "pairs base t=%d FAILED:\n%s",
                                t_idx, traceback.format_exc(),
                            )

                    if run_rlm and rlm_project is not None:
                        t_q = time.monotonic()
                        try:
                            pred, toks = call_rlm(qtext, rlm_project)
                            pred_pairs = parse_pairs_from_text(pred)
                            s = f1_score(pred_pairs, gold_pairs)
                            pairs_rlm.append(s)
                            results.append({
                                "benchmark": "oolong_pairs",
                                "model": f"rlm:{model}",
                                "context_len": ctx_len,
                                "context_window_id": ctx_id,
                                "task_id": f"pairs_{t_idx}",
                                "score": s,
                            })
                            _progress("rlm:pairs", hl, s, time.monotonic() - t_q, toks)
                            log.debug(
                                "pairs rlm t=%d f1=%.3f |pred|=%d |gold|=%d",
                                t_idx, s, len(pred_pairs), len(gold_pairs),
                            )
                        except Exception:
                            _progress("rlm:pairs", hl, 0.0, time.monotonic() - t_q)
                            log.error(
                                "pairs rlm t=%d FAILED:\n%s",
                                t_idx, traceback.format_exc(),
                            )

                # --- Per-window status line ---
                elapsed = time.monotonic() - t_win
                parts = [f"  {hl:>4s} [{w_idx}/{len(windows)}]"]
                if ool_base:
                    avg = 100 * sum(ool_base) / len(ool_base)
                    parts.append(f"base:ool={avg:.0f}%")
                if ool_rlm:
                    avg = 100 * sum(ool_rlm) / len(ool_rlm)
                    parts.append(f"rlm:ool={avg:.0f}%")
                if pairs_base:
                    avg = 100 * sum(pairs_base) / len(pairs_base)
                    parts.append(f"base:pairs={avg:.0f}%")
                if pairs_rlm:
                    avg = 100 * sum(pairs_rlm) / len(pairs_rlm)
                    parts.append(f"rlm:pairs={avg:.0f}%")
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
