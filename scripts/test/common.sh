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
export PYTHON_BIN  # the bundler builds the file tracer with this interpreter's zig

# The paths a run is narrowed to: test-python.sh and test-global.sh take them as arguments,
# and only the test files at or under one of them run. Empty, the default, runs every file.
# CI passes what scripts/github-workflows/select_checks.py selected for a change.
TEST_PATHS=()
SELECTED_TEST_FILES=0

# The packaged runtime (packages/cadgen/src/cadgen/_runtime) is BUILT, never committed,
# so a fresh checkout has none of it -- the snapshot suites drive the browser bundle and
# every build loads the file tracer.
# Building it is idempotent and fast once the pinned toolchains are in place, but it is
# not free, so this only runs when an output is missing (or the tracer's source is newer).
#
# The stages are asked for by name rather than going through bundle.sh: the tests read
# exactly these, and the viewer stage is a vite build of apps/web that needs that app's
# node_modules -- which a Python-only checkout has no reason to install.
ensure_packaged_runtime() {
  local runtime="$REPO_ROOT/packages/cadgen/src/cadgen/_runtime"
  local name
  # PYTHON_TEST_RUNTIME=0: the selected tests read none of it, and the interpreter may lack
  # what building it takes. A test that does read it then fails on the missing file.
  if [ "${PYTHON_TEST_RUNTIME:-1}" = "0" ]; then
    return 0
  fi
  for name in browser/snapshot-render.js browser/render.html; do
    if [ ! -f "$runtime/$name" ]; then
      section "Building cadgen's packaged runtime (missing $name)"
      "$REPO_ROOT/scripts/bundle/cadgen-runtime.sh" --browser
      break
    fi
  done
  # Every build loads the file tracer, so every suite that builds needs the one this
  # interpreter loads, rebuilt when its source is newer.
  local tracer
  tracer="$runtime/native/$(PYTHONPATH="$REPO_ROOT/packages/cadgen/src" "$PYTHON_BIN" -c \
    "from cadgen._internal.filetrace import _library_name; print(_library_name())")"
  if [ ! -f "$tracer" ] || [ "$REPO_ROOT/packages/cadgen/native/filetrace.c" -nt "$tracer" ]; then
    section "Building cadgen's file tracer"
    "$REPO_ROOT/scripts/bundle/cadgen-runtime.sh" --native-host
  fi
}

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
  # Each test FILE runs in its own interpreter with its own fresh store, CADGEN_TEST_JOBS
  # at a time (default: the machine's cores). Modules cannot see one another's builds,
  # and a module that spawns workers or a daemon does not hold the rest of the suite.
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
