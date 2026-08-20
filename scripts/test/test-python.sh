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

# Turn the render-package write-lock assertion into a hard failure for tests. In
# production require_write_lock() only warns -- a missing lock must never be the reason a
# user's build fails -- so CI is the only place the contract is actually enforced.
export CADGEN_STRICT_LOCKS=1

run_suite "cadgen package Python tests" "tests/python/packages/cadgen" "packages/cadgen/src"

while IFS= read -r skill; do
  test_dir="tests/python/skills/$skill"
  if [ -d "$test_dir" ]; then
    skill_paths=("skills/$skill/scripts")
    if [ "$skill" = "cad" ] || [ "$skill" = "dxf" ]; then
      skill_paths+=("skills/$skill/scripts/packages/cadgen/src")
    fi
    run_suite "$skill skill Python tests" "$test_dir" "${skill_paths[@]}"
  fi
done < <("$LIST_SKILLS_SCRIPT")

run_suite "MoveIt2 server Python tests" "tests/python/viewer/moveit2_server" "viewer/moveit2_server"

# The CAD Viewer backend keeps its tests beside the package it covers rather
# than under tests/, so name the directory explicitly. It owns the only cross-process
# coverage of the generation lock (test_artifact.py drives a real second process and
# SIGKILLs it), which is why it must run in CI.
# packages/cadgen/src is on the path because the viewer server imports cadgen's
# stdlib-only modules directly (coordination, source_hash) rather than reimplementing
# them. Without it an installed/editable cadgen from another checkout wins and the
# coordination package is missing.
run_suite "CAD Viewer backend Python tests" "viewer/server_py/tests" "viewer" "packages/cadgen/src"

if [ "${#failed_suites[@]}" -gt 0 ]; then
  printf '\n==> FAILING SUITES (%d)\n' "${#failed_suites[@]}"
  printf '  %s\n' "${failed_suites[@]}"
  exit 1
fi
