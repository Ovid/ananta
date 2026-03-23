# Agentic Code Review: ovid/explorer-launchers-to-python

**Date:** 2026-03-22 15:32:48
**Branch:** ovid/explorer-launchers-to-python -> main
**Commit:** 2a8e57f6c80d6d55c590393330e4aca860f182a9
**Files changed:** 15 | **Lines changed:** +1814 / -292
**Diff size category:** Large

## Executive Summary

Clean refactor that moves explorer launcher bash logic into a testable Python module. The core `launcher.py` and its tests are well-structured. However, two stale references to deleted files were missed (a bats test file and an explorer README), and the Docker-related tests are environment-dependent due to missing `shutil.which` mocks. One subprocess error path (`build_frontend`) lacks the same graceful handling found elsewhere in the module.

## Critical Issues

### [C1] Stale bats test file sources deleted `scripts/common.sh`
- **File:** `tests/scripts/test_common.bats:4`
- **Bug:** The file sets `COMMON="$BATS_TEST_DIRNAME/../../scripts/common.sh"` and all 13 tests source it. `scripts/common.sh` was deleted in this branch.
- **Impact:** All 13 bats tests will fail on every run. CI breakage if bats tests are in the test suite.
- **Suggested fix:** Delete `tests/scripts/test_common.bats` — its coverage is now provided by `tests/unit/explorers/test_launcher.py`.
- **Confidence:** High
- **Found by:** Contract & Integration

## Important Issues

### [I1] `arxiv-explorer/README.md` references deleted `examples/arxiv-explorer.sh`
- **File:** `arxiv-explorer/README.md:23`
- **Bug:** Setup instructions tell users to run `./examples/arxiv-explorer.sh`, which was deleted in this branch.
- **Impact:** Broken first-run instructions for anyone reading the arxiv-explorer README.
- **Suggested fix:** Update to `./arxiv-explorer/arxiv-explorer.sh`.
- **Confidence:** High
- **Found by:** Contract & Integration

### [I2] Docker-related tests missing `shutil.which` mock — environment-dependent
- **File:** `tests/unit/explorers/test_launcher.py:109-119` (TestCheckDockerRunning) and `tests/unit/explorers/test_launcher.py:128-155` (TestEnsureSandboxImage)
- **Bug:** `test_docker_running`, `test_docker_not_running`, `test_image_exists`, `test_image_missing_build_succeeds`, and `test_image_missing_build_fails` mock `subprocess.run` but not `shutil.which`. The production code calls `shutil.which("docker")` first and returns `None` early if Docker is absent. On machines without Docker, these tests either pass vacuously or fail outright (e.g., `test_docker_not_running` expects an error string but gets `None`).
- **Impact:** Tests are unreliable across environments. The `test_docker_not_installed` variants in both classes do mock `shutil.which` correctly, showing the pattern is known but inconsistently applied.
- **Suggested fix:** Add `@patch("ananta.explorers.launcher.shutil.which", return_value="/usr/bin/docker")` to the affected tests.
- **Confidence:** High
- **Found by:** Logic & Correctness, Contract & Integration, Concurrency & State (5 specialists agreed)

### [I3] `build_frontend()` lets `CalledProcessError` propagate as raw traceback
- **File:** `src/ananta/explorers/launcher.py:117-121`
- **Bug:** `build_frontend` calls `subprocess.run(["npm", ...], check=True)` without catching `CalledProcessError`. A failed npm command produces a Python traceback instead of a clean error message. This contrasts with `ensure_sandbox_image` and `check_docker_running`, which both catch subprocess failures gracefully.
- **Impact:** Users see a raw traceback on npm build failure instead of the `[ananta] Cannot start...` pattern used everywhere else.
- **Suggested fix:** Wrap npm subprocess calls in try/except, or catch the exception in `launch()` around the `build_frontend` call.
- **Confidence:** Medium
- **Found by:** Logic & Correctness, Error Handling & Edge Cases

### [I4] Hardcoded sandbox image name duplicates config constant
- **File:** `src/ananta/explorers/launcher.py:75`
- **Bug:** `os.environ.get("ANANTA_SANDBOX_IMAGE", "ananta-sandbox")` hardcodes the default `"ananta-sandbox"`. The canonical default lives in `src/ananta/config.py:44` as `AnantaConfig.sandbox_image`. If the default changes in one place, the other silently diverges.
- **Impact:** Silent behavior mismatch if the default image name is ever changed in config.py.
- **Suggested fix:** Import and use the constant from `AnantaConfig`, or extract a shared constant.
- **Confidence:** Medium
- **Found by:** Contract & Integration

## Suggestions

- `launcher.py:136-138` — `project_root` auto-detection via `Path(__file__).resolve().parents[3]` assumes editable install layout and is never validated. Consider checking for `pyproject.toml` at the resolved path.
- `launcher.py:158` — `config.entry_point` is not existence-checked before `subprocess.run`. A missing binary produces `FileNotFoundError` instead of a clean preflight error. Consider adding it to `run_preflight`.
- The three shell shims (`*-explorer.sh`) are nearly identical (differ only in `PIP_EXTRA` and `APP_SLUG`). Acceptable given they're thin bootstrap scripts, but a single parameterized script would reduce maintenance.

## Plan Alignment

- **Implemented:** All 11 tasks from the implementation plan are complete. LauncherConfig, all preflight checks, frontend build, launch orchestration, per-explorer configs, bash shim rewrites, file deletions, README/CHANGELOG updates, and lint pass.
- **Not yet implemented:** None — all planned work is present.
- **Deviations:** Implementation correctly adds `sys.exit(launch(config))` in launch.py files where the design doc example omitted it. This is an improvement. Decorator order in one test differs from plan but is functionally equivalent.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment
- **Scope:** 15 changed files + `tests/scripts/test_common.bats`, `arxiv-explorer/README.md`, `src/ananta/config.py` (adjacent)
- **Raw findings:** 26 (before verification)
- **Verified findings:** 8 (after verification)
- **Filtered out:** 18
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** docs/plans/2026-03-22-python-launcher-design.md, docs/plans/2026-03-22-python-launcher-implementation.md
