#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  elif [ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
  else
    PYTHON_BIN="python3"
  fi
fi
export PYTHON_BIN

# Each test file receives a fixed, free CADGEN_PORT from unittest_files.py.
# Nor does it keep a standby worker (``daemon.standby``): each daemon a test starts would load the
# kernel twice over (2.4 s and 440 MB a standby) on runners short of memory. Its own tests set it on.
export CADGEN_ENGINE_STANDBY=0
# A test's process that dies in native code (a worker's access violation as it loads the kernel)
# prints its Python stack before it goes: workers inherit it from the run, so the model log the
# client prints, and so the failing test's output, says where.
export PYTHONFAULTHANDLER=1

# The paths a run is narrowed to: test-python.sh and test-global.sh take them as arguments,
# and only the test files at or under one of them run. Empty, the default, runs every file.
# CI passes what scripts/github-workflows/select_checks.py selected for a change.
TEST_PATHS=()
SELECTED_TEST_FILES=0

section() {
  # A log line, not a result: --print-weights writes the per-file costs to stdout.
  printf '\n==> %s\n' "$1" >&2
}

run_python_unittest() {
  local name="$1"
  local start_dir="$2"
  shift 2
  local test_files=()
  local python_path="$REPO_ROOT:$REPO_ROOT/$start_dir"
  local path_entry

  section "$name"

  local found=0
  while IFS= read -r test_file; do
    found=$((found + 1))
    if is_selected_test "$test_file"; then
      test_files+=("$test_file")
    fi
  done < <(find "$REPO_ROOT/$start_dir" -name 'test*.py' -print | sort)

  if [ "$found" -eq 0 ]; then
    echo "No Python tests found under $start_dir" >&2
    return 1
  fi
  if [ "${#test_files[@]}" -eq 0 ]; then
    echo "   (none of the selected paths)" >&2
    return 0
  fi
  SELECTED_TEST_FILES=$((SELECTED_TEST_FILES + ${#test_files[@]}))

  for path_entry in "$@"; do
    if [[ "$path_entry" = /* ]]; then
      python_path="$python_path:$path_entry"
    else
      python_path="$python_path:$REPO_ROOT/$path_entry"
    fi
  done

  # Not `-m unittest "${test_files[@]}"`: that names a failed import after the last
  # dotted component only, so the several test_cli.py files here all fail as
  # `_FailedTest.test_cli`. unittest_files.py loads each file under its full dotted
  # path relative to the repo root and names an import failure by that path + file.
  #
  # Each test FILE runs in its own interpreter, CADGEN_TEST_JOBS at a time (default: the
  # machine's cores), with an engine directory of its own: a build it asks for without naming
  # a daemon runs on one of that file's alone, stopped when the file ends, so a module that
  # starts workers or a daemon does not hold the rest of the suite.
  # PYTHON_TEST_PRINT_WEIGHTS is how --print-weights reaches the runner without every
  # caller growing a flag.
  local extra=()
  if [ -n "${PYTHON_TEST_PRINT_WEIGHTS:-}" ]; then
    extra+=(--print-weights)
  fi

  PYTHONPATH="$python_path${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" "$SCRIPT_DIR/unittest_files.py" --top "$REPO_ROOT" \
      --jobs "${CADGEN_TEST_JOBS:-$(test_jobs)}" ${extra[@]+"${extra[@]}"} "${test_files[@]}"
}

is_selected_test() {
  local file="$1"
  local path
  [ "${#TEST_PATHS[@]}" -eq 0 ] && return 0
  for path in "${TEST_PATHS[@]}"; do
    path="$REPO_ROOT/${path%/}"
    if [ "$file" = "$path" ] || [[ "$file" == "$path"/* ]]; then
      return 0
    fi
  done
  return 1
}

# A narrowed run that matched nothing selected a path that holds no test: say so, rather
# than pass having run nothing.
require_selected_tests() {
  if [ "${#TEST_PATHS[@]}" -gt 0 ] && [ "$SELECTED_TEST_FILES" -eq 0 ]; then
    echo "No test file at or under: ${TEST_PATHS[*]}" >&2
    exit 1
  fi
}

test_jobs() {
  # The core count, portably; one job when it cannot be read.
  "$PYTHON_BIN" -c 'import os; print(os.cpu_count() or 1)' 2>/dev/null || echo 1
}
