#!/usr/bin/env bats
# Tests for scripts/common.sh preflight validation.

COMMON="$BATS_TEST_DIRNAME/../../scripts/common.sh"

setup() {
    # Minimal config required by common.sh
    export PROJECT_ROOT="$BATS_TEST_DIRNAME/../.."
    export APP_NAME="Test Explorer"
    export APP_SLUG="test-explorer"
    export PIP_EXTRA="dev"
    export ENTRY_POINT="echo"
    export FRONTEND_DIR="$BATS_TEST_TMPDIR/frontend"
    mkdir -p "$FRONTEND_DIR/dist"
}

# --- require_command ---

@test "require_command adds error for missing command" {
    source "$COMMON"
    ERRORS=()
    require_command "nonexistent_cmd_xyz" "https://example.com"
    [ ${#ERRORS[@]} -eq 1 ]
    [[ "${ERRORS[0]}" == *"Install nonexistent_cmd_xyz"* ]]
}

@test "require_command succeeds for existing command" {
    source "$COMMON"
    ERRORS=()
    require_command "bash" "https://example.com"
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- require_env ---

@test "require_env adds error for unset variable" {
    unset TOTALLY_UNSET_VAR
    source "$COMMON"
    ERRORS=()
    require_env "TOTALLY_UNSET_VAR" "export TOTALLY_UNSET_VAR=value"
    [ ${#ERRORS[@]} -eq 1 ]
    [[ "${ERRORS[0]}" == *"Set TOTALLY_UNSET_VAR"* ]]
}

@test "require_env adds error for empty variable" {
    export EMPTY_VAR=""
    source "$COMMON"
    ERRORS=()
    require_env "EMPTY_VAR" "export EMPTY_VAR=value"
    [ ${#ERRORS[@]} -eq 1 ]
}

@test "require_env passes for set variable" {
    export PRESENT_VAR="hello"
    source "$COMMON"
    ERRORS=()
    require_env "PRESENT_VAR" "export PRESENT_VAR=value"
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- check_python_version ---

@test "check_python_version passes for current python" {
    source "$COMMON"
    ERRORS=()
    check_python_version
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- report_and_exit ---

@test "report_and_exit does nothing when no errors" {
    source "$COMMON"
    ERRORS=()
    run report_and_exit
    [ "$status" -eq 0 ]
}

@test "report_and_exit exits 1 and prints errors" {
    source "$COMMON"
    ERRORS=("  - Error one" "  - Error two")
    run report_and_exit
    [ "$status" -eq 1 ]
    [[ "$output" == *"Cannot start Test Explorer"* ]]
    [[ "$output" == *"Error one"* ]]
    [[ "$output" == *"Error two"* ]]
}

# --- Error collection (multiple failures) ---

@test "multiple failures are all collected" {
    unset ANANTA_API_KEY
    unset ANANTA_MODEL
    source "$COMMON"
    ERRORS=()
    require_command "nonexistent_cmd_xyz" "https://example.com"
    require_env "ANANTA_API_KEY" "export ANANTA_API_KEY=<your-key>"
    require_env "ANANTA_MODEL" "export ANANTA_MODEL=<model-name>"
    [ ${#ERRORS[@]} -eq 3 ]
}

# --- Flag parsing ---

@test "--rebuild flag is stripped from args" {
    export ANANTA_API_KEY="test"
    export ANANTA_MODEL="test"
    set -- --port 9000 --rebuild --no-browser
    source "$COMMON"
    [ "$REBUILD" = true ]
    [ ${#ANANTA_ARGS[@]} -eq 3 ]
    [[ "${ANANTA_ARGS[*]}" == "--port 9000 --no-browser" ]]
}

@test "args without --rebuild are passed through" {
    export ANANTA_API_KEY="test"
    export ANANTA_MODEL="test"
    set -- --port 9000
    source "$COMMON"
    [ "$REBUILD" = false ]
    [ ${#ANANTA_ARGS[@]} -eq 2 ]
}

# --- stderr filter ---

@test "stderr_filter suppresses Exception-ignored blocks" {
    source "$COMMON"
    input="$(cat <<'BLOCK'
INFO:     Shutting down
Exception ignored while finalizing file <http.client.HTTPResponse object at 0x10fef89a0>:
Traceback (most recent call last):
  File "/opt/homebrew/lib/python3.14/http/client.py", line 437, in close
    super().close()
  File "/opt/homebrew/lib/python3.14/http/client.py", line 450, in flush
    self.fp.flush()
ValueError: I/O operation on closed file.
INFO:     Finished server process [66553]
BLOCK
)"
    result="$(printf '%s\n' "$input" | stderr_filter)"
    [[ "$result" == *"Shutting down"* ]]
    [[ "$result" == *"Finished server process"* ]]
    [[ "$result" != *"Exception ignored"* ]]
    [[ "$result" != *"ValueError"* ]]
    [[ "$result" != *"Traceback"* ]]
}

@test "stderr_filter preserves normal error output" {
    source "$COMMON"
    input="ERROR: something went wrong"
    result="$(printf '%s\n' "$input" | stderr_filter)"
    [[ "$result" == *"something went wrong"* ]]
}
