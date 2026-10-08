#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

# scripts/test/test-global.sh [PATH...]: PATHs narrow the suite to those test files.
for argument in "$@"; do
  case "$argument" in
    -*) echo "test-global.sh: unknown argument $argument" >&2; exit 2 ;;
    *) TEST_PATHS+=("$argument") ;;
  esac
done

ensure_packaged_runtime

# The checkout's own cadgen, as test-python.sh does: without it a worktree run tests
# whatever the venv's editable install points at (the primary checkout).
run_python_unittest "Global policy tests" "tests/python/global" "packages/cadgen/src"
require_selected_tests
