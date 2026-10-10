#!/usr/bin/env bash
set -euo pipefail

# The suites that need WireViz itself: the `wireviz` command (a separate program cadgen runs,
# never imports) and the Graphviz `dot` it draws with. They live apart from the cadgen
# package suite because that one runs on machines without WireViz (its Windows job among
# them); everything here is cadgen.wireviz driven end to end through a real WireViz. Boards
# come from the tests' own tiny library, so KiCad is not needed.
#
#   scripts/test/test-harness.sh
#
# WireViz and Graphviz must be installed (cadgen finds wireviz on PATH, in ~/.local/bin, or
# at CADGEN_WIREVIZ, and dot on PATH or where Graphviz installs). A missing one fails the run
# rather than skipping it.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cadgen.wireviz.install import find_wireviz; install = find_wireviz(); print(f'WireViz {install.version}: {install.cli}; Graphviz {install.graphviz_version}: {install.dot}')" \
  || { echo "test-harness.sh: WireViz and Graphviz are required for these suites" >&2; exit 1; }

ensure_packaged_runtime

# The same isolated store the cadgen suite uses: builds here must not read or write the
# developer's ~/.cache/cadgen.
CADGEN_TEST_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-test-store.XXXXXX")"
trap 'rm -rf "$CADGEN_TEST_CACHE_DIR"' EXIT
export CADGEN_CACHE_DIR="$CADGEN_TEST_CACHE_DIR"

run_python_unittest "Harness Python tests" "tests/python/packages/harness" "packages/cadgen/src"
