#!/usr/bin/env bash
set -euo pipefail

# The repo's Python suites.
#
#   scripts/test/test-python.sh [--keep-going] [--select GROUP] [--shard I/N] [--print-weights]
#
# --select picks one group instead of all of them:
#   cadgen   the cadgen package suite, the CAD Viewer backend included (92% of the time)
#   viewer   the CAD Viewer backend alone (tests/python/packages/cadgen/viewer)
#   skills   every skill's suite
#   all      cadgen + skills (the default)
#
# --shard I/N splits the SELECTED group's files across N runs; see unittest_files.py.
# It is rejected for `skills`, whose suites are separate runs of a few files each --
# sharding them would mean asking one shard to run a suite that is not its own.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"

# --keep-going: run every suite and report all of them, instead of stopping at the first
# failure. Opt-in, because stopping early is the right default for a developer waiting on a
# run. It is for CI on a platform being brought up, where the failures are independent and
# one round per suite means one ~10 minute round trip per suite.
KEEP_GOING=0
SELECT="all"
export PYTHON_TEST_SHARD="${PYTHON_TEST_SHARD:-}"
export PYTHON_TEST_PRINT_WEIGHTS="${PYTHON_TEST_PRINT_WEIGHTS:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --keep-going) KEEP_GOING=1 ;;
    --select) SELECT="${2:?--select wants a group}"; shift ;;
    --select=*) SELECT="${1#--select=}" ;;
    --shard) PYTHON_TEST_SHARD="${2:?--shard wants I/N}"; shift ;;
    --shard=*) PYTHON_TEST_SHARD="${1#--shard=}" ;;
    --print-weights) PYTHON_TEST_PRINT_WEIGHTS=1 ;;
    *) echo "test-python.sh: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

case "$SELECT" in
  all|cadgen|viewer|skills) ;;
  *) echo "test-python.sh: --select wants all|cadgen|viewer|skills, not '$SELECT'" >&2; exit 2 ;;
esac

if [ -n "$PYTHON_TEST_SHARD" ] && { [ "$SELECT" = "skills" ] || [ "$SELECT" = "all" ]; }; then
  echo "test-python.sh: --shard needs --select cadgen or --select viewer" >&2
  exit 2
fi

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

# Isolate the shared caches (component store + op-memo disk tier) from the
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
# apps/viewer is read by any other cadgen test.
if [ "$SELECT" = "viewer" ]; then
  run_suite "CAD Viewer backend Python tests" "tests/python/packages/cadgen/viewer" "packages/cadgen/src"
fi

if [ "$SELECT" = "all" ] || [ "$SELECT" = "skills" ]; then
  while IFS= read -r skill; do
    test_dir="tests/python/skills/$skill"
    if [ -d "$test_dir" ]; then
      # Skills no longer vendor cadgen; they import the distribution. In a checkout that is
      # the repo's own source, so put it on the path rather than depending on whatever the
      # interpreter happens to have installed.
      run_suite "$skill skill Python tests" "$test_dir" \
        "skills/$skill/scripts" "packages/cadgen/src"
    fi
  done < <("$LIST_SKILLS_SCRIPT")
fi

if [ "${#failed_suites[@]}" -gt 0 ]; then
  printf '\n==> FAILING SUITES (%d)\n' "${#failed_suites[@]}"
  printf '  %s\n' "${failed_suites[@]}"
  exit 1
fi
