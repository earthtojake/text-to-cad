#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"

# --keep-going: run every suite and report all of them, instead of stopping at the first
# failure. Opt-in, because stopping early is the right default for a developer waiting on a
# run. It is for CI on a platform being brought up, where the failures are independent and
# one round per suite means one ~10 minute round trip per suite.
KEEP_GOING=0
if [ "${1:-}" = "--keep-going" ]; then
  KEEP_GOING=1
  shift
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

# Isolate the shared caches (component store + op-memo disk tier) from the
# developer's real ~/.cache/cadgen: tests assert exact built/reused counts and
# byte-level outputs, and a populated user store would satisfy builds the test
# expects to run (and test runs would pollute the user's cache in return).
CADGEN_TEST_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-test-store.XXXXXX")"
trap 'rm -rf "$CADGEN_TEST_CACHE_DIR"' EXIT
export CADGEN_CACHE_DIR="$CADGEN_TEST_CACHE_DIR"

# The cadgen package suite includes the CAD Viewer backend (tests/python/packages/cadgen/viewer):
# the server is cadgen.viewer, and this is the one runner that reaches every pull request --
# through test.sh on Linux and directly in the Windows job. Windows matters most of all for the
# viewer: path handling, locks, subprocesses and file URLs are precisely the class of bug that
# has only ever shown up there.
run_suite "cadgen package Python tests" "tests/python/packages/cadgen" "packages/cadgen/src"

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

if [ "${#failed_suites[@]}" -gt 0 ]; then
  printf '\n==> FAILING SUITES (%d)\n' "${#failed_suites[@]}"
  printf '  %s\n' "${failed_suites[@]}"
  exit 1
fi
