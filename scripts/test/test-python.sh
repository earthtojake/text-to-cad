#!/usr/bin/env bash
set -euo pipefail

# The repo's Python suites.
#
#   scripts/test/test-python.sh [--keep-going] [--select GROUP] [--print-weights] [--kernel FOLDER] [PATH...]
#
# --select picks one group instead of all of them:
#   cadgen   the packages' suites: the library's, the server's (the viewer backend included)
#            and the shim's (92% of the time)
#   viewer   the viewer backend alone (tests/python/packages/cad_server/viewer)
#   skills   every skill's suite
#   all      cad + skills (the default)
#
# --print-weights prints one `WEIGHT<TAB>path<TAB>seconds` line per slow file on
# stdout: the first thing to read when a run is slow.
#
# --kernel FOLDER runs the suites on the WebAssembly kernel in FOLDER (a kernel folder: its
# kernel.json and bin/python): every test's server runs its kernel processes there, by the
# setting a person chooses it with, which each test's state folder is given as it is
# registered (tests/python/support/engine_daemon.py). The tests' own processes stay on this
# interpreter. docs/contributing/testing.md says what such a run shows.
#
# PATHs narrow the group to the test files at or under them (repo-relative); CI passes
# the files and directories a change selected.
#
# CAD_TEST_SHARD=I/N runs shard I of N (from 1) of each suite's selected files: sorted by
# path, the k-th (from 0) is shard k%N+1's, so the N shards run every file exactly once,
# and a shard that none falls to passes. CI splits a long suite across jobs by it.

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
    --kernel) CAD_TEST_KERNEL="${2:?--kernel wants a kernel folder}"; shift ;;
    --kernel=*) CAD_TEST_KERNEL="${1#--kernel=}" ;;
    -*) echo "test-python.sh: unknown argument $1" >&2; exit 2 ;;
    *) TEST_PATHS+=("$1") ;;
  esac
  shift
done

if [ -n "${CAD_TEST_KERNEL:-}" ]; then
  # Its launcher is bin/python, on Windows bin/python.cmd.
  if [ ! -f "$CAD_TEST_KERNEL/kernel.json" ] || { [ ! -x "$CAD_TEST_KERNEL/bin/python" ] && [ ! -f "$CAD_TEST_KERNEL/bin/python.cmd" ]; }; then
    echo "test-python.sh: --kernel wants a kernel folder (its kernel.json and bin/python), not '$CAD_TEST_KERNEL'" >&2
    exit 2
  fi
  CAD_TEST_KERNEL="$(cd "$CAD_TEST_KERNEL" && pwd)"
  export CAD_TEST_KERNEL
fi

case "$SELECT" in
  all|cadgen|viewer|skills) ;;
  *) echo "test-python.sh: --select wants all|cadgen|viewer|skills, not '$SELECT'" >&2; exit 2 ;;
esac

failed_suites=()

# A suite in which a file hung (unittest_files.py's HUNG_EXIT, 3) ends the run even so: what hung
# one suite's file likely hangs the next's, and each would wait out its guard to the job's timeout.
run_suite() {
  local status=0
  if [ "$KEEP_GOING" -eq 1 ]; then
    run_python_unittest "$@" || status=$?
    if [ "$status" -eq 3 ]; then
      printf '\n==> A FILE HUNG in: %s. No further suite runs.\n' "$1" >&2
      exit 1
    elif [ "$status" -ne 0 ]; then
      failed_suites+=("$1")
    fi
  else
    run_python_unittest "$@"
  fi
}

cd "$REPO_ROOT"

# The packages' suites, one each: the library's (cad), the server's (cad-server: the CAD
# Viewer backend, cad_server.viewer, among them) and the shim's (cad-mcp). This is the one
# runner that reaches every pull request. Windows matters most of all for the viewer: path
# handling, locks, subprocesses and file URLs are precisely the class of bug that has only ever
# shown up there.
if [ "$SELECT" = "all" ] || [ "$SELECT" = "cadgen" ]; then
  run_suite "cad (the library) Python tests" "tests/python/packages/cad" "${PACKAGE_SOURCES[@]}"
  run_suite "cad-server Python tests" "tests/python/packages/cad_server" "${PACKAGE_SOURCES[@]}"
  run_suite "cad-mcp (the shim) Python tests" "tests/python/packages/cad_mcp" "${PACKAGE_SOURCES[@]}"
fi

# The backend alone, for a pull request that only moves the Viewer's client: nothing under
# apps/web is read by any other package test.
if [ "$SELECT" = "viewer" ]; then
  run_suite "Viewer backend Python tests" "tests/python/packages/cad_server/viewer" "${PACKAGE_SOURCES[@]}"
fi

if [ "$SELECT" = "all" ] || [ "$SELECT" = "skills" ]; then
  for skill_md in skills/*/SKILL.md; do
    skill="$(basename "$(dirname "$skill_md")")"
    test_dir="tests/python/skills/$skill"
    if [ -d "$test_dir" ]; then
      # Skills vendor none of the packages; they import the distributions. In a checkout those
      # are the repo's own source, so put it on the path rather than depending on whatever the
      # interpreter happens to have installed.
      run_suite "$skill skill Python tests" "$test_dir" \
        "skills/$skill/scripts" "${PACKAGE_SOURCES[@]}"
    fi
  done
fi

require_selected_tests

if [ "${#failed_suites[@]}" -gt 0 ]; then
  printf '\n==> FAILING SUITES (%d)\n' "${#failed_suites[@]}"
  printf '  %s\n' "${failed_suites[@]}"
  exit 1
fi
