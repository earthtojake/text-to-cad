#!/usr/bin/env bash
set -euo pipefail

# The repo's Python suites.
#
#   scripts/test/test-python.sh [--keep-going] [--select GROUP] [--print-weights] [PATH...]
#
# --select picks one group instead of all of them:
#   cadgen   the cadgen package suite, the CAD Viewer backend included (92% of the time)
#   viewer   the CAD Viewer backend alone (tests/python/packages/cadgen/viewer)
#   skills   every skill's suite
#   cloud    the hosted CAD server's sandbox runner (tests/python/apps/cloud)
#   all      cadgen + skills + cloud (the default)
#
# --print-weights prints one `WEIGHT<TAB>path<TAB>seconds` line per slow file on
# stdout: the first thing to read when a run is slow.
#
# PATHs narrow the group to the test files at or under them (repo-relative); CI passes
# the files and directories a change selected.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# --keep-going: run every suite and report all of them, instead of stopping at the first
# failure. Opt-in, because stopping early is the right default for a developer waiting on a
# run. It is for CI on a platform being brought up, where the failures are independent and
# one round per suite means one ~10 minute round trip per suite.
KEEP_GOING=0
SELECT="all"
export PYTHON_TEST_PRINT_WEIGHTS="${PYTHON_TEST_PRINT_WEIGHTS:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --keep-going) KEEP_GOING=1 ;;
    --select) SELECT="${2:?--select wants a group}"; shift ;;
    --select=*) SELECT="${1#--select=}" ;;
    --print-weights) PYTHON_TEST_PRINT_WEIGHTS=1 ;;
    -*) echo "test-python.sh: unknown argument $1" >&2; exit 2 ;;
    *) TEST_PATHS+=("$1") ;;
  esac
  shift
done

case "$SELECT" in
  all|cadgen|viewer|skills|cloud) ;;
  *) echo "test-python.sh: --select wants all|cadgen|viewer|skills|cloud, not '$SELECT'" >&2; exit 2 ;;
esac

failed_suites=()

run_suite() {
  if [ "$KEEP_GOING" -eq 1 ]; then
    run_python_unittest "$@" || failed_suites+=("$1")
  else
    run_python_unittest "$@"
  fi
}

cd "$REPO_ROOT"

ensure_packaged_runtime

# Isolate the shared store from the
# developer's real ~/.cache/cadgen: tests assert exact built/reused counts and
# byte-level outputs, and a populated user store would satisfy builds the test
# expects to run (and test runs would pollute the user's cache in return).
CADGEN_TEST_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-test-store.XXXXXX")"
trap 'rm -rf "$CADGEN_TEST_CACHE_DIR"' EXIT
export CADGEN_CACHE_DIR="$CADGEN_TEST_CACHE_DIR"

# The cadgen package suite includes the CAD Viewer backend (tests/python/packages/cadgen/viewer):
# the server is cadgen.viewer, and this is the one runner that reaches every pull request.
# Windows matters most of all for the viewer: path handling, locks, subprocesses and file
# URLs are precisely the class of bug that has only ever shown up there.
if [ "$SELECT" = "all" ] || [ "$SELECT" = "cadgen" ]; then
  run_suite "cadgen package Python tests" "tests/python/packages/cadgen" "packages/cadgen/src"
fi

# The backend alone, for a pull request that only moves the Viewer's client: nothing under
# apps/web is read by any other cadgen test.
if [ "$SELECT" = "viewer" ]; then
  run_suite "CAD Viewer backend Python tests" "tests/python/packages/cadgen/viewer" "packages/cadgen/src"
fi

if [ "$SELECT" = "all" ] || [ "$SELECT" = "skills" ]; then
  for skill_md in skills/*/SKILL.md; do
    skill="$(basename "$(dirname "$skill_md")")"
    test_dir="tests/python/skills/$skill"
    if [ -d "$test_dir" ]; then
      # Skills no longer vendor cadgen; they import the distribution. In a checkout that is
      # the repo's own source, so put it on the path rather than depending on whatever the
      # interpreter happens to have installed.
      run_suite "$skill skill Python tests" "$test_dir" \
        "skills/$skill/scripts" "packages/cadgen/src"
    fi
  done
fi

# The hosted CAD server's runner: the one Python file apps/cloud ships into a sandbox, run here
# against this checkout's cadgen as a sandbox runs it against the released one.
if [ "$SELECT" = "all" ] || [ "$SELECT" = "cloud" ]; then
  run_suite "cloud runner Python tests" "tests/python/apps/cloud" "packages/cadgen/src"
fi

require_selected_tests

if [ "${#failed_suites[@]}" -gt 0 ]; then
  printf '\n==> FAILING SUITES (%d)\n' "${#failed_suites[@]}"
  printf '  %s\n' "${failed_suites[@]}"
  exit 1
fi
