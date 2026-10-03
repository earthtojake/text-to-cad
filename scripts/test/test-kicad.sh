#!/usr/bin/env bash
set -euo pipefail

# The suites that need KiCad itself: kicad-cli (zone fill, ERC, DRC, plots, Gerbers, the
# populated board's STEP), the ngspice library KiCad ships, and Freerouting for
# board.autoroute(). They live apart from the cadgen package suite because that one runs on
# machines without KiCad (its Windows job among them); everything here is cadgen.kicad
# driven end to end through a real KiCad.
#
#   scripts/test/test-kicad.sh
#
# KiCad 10 must be installed (cadgen finds kicad-cli on PATH, in the usual install
# folders, or at CADGEN_KICAD_CLI), and Freerouting (its app, or its jar with Java 25:
# CADGEN_FREEROUTING, CADGEN_JAVA). A missing one fails the run rather than skipping it.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cadgen.kicad.install import find_kicad; install = find_kicad(); print(f'KiCad {install.version}: {install.cli}')" \
  || { echo "test-kicad.sh: KiCad 10 is required for these suites" >&2; exit 1; }
PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cadgen.kicad.route import find_freerouting; router = find_freerouting(); print(f'Freerouting: {router.location}')" \
  || { echo "test-kicad.sh: Freerouting is required for the autoroute suite" >&2; exit 1; }

ensure_packaged_runtime

# The same isolated store the cadgen suite uses: builds here must not read or write the
# developer's ~/.cache/cadgen.
CADGEN_TEST_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-test-store.XXXXXX")"
trap 'rm -rf "$CADGEN_TEST_CACHE_DIR"' EXIT
export CADGEN_CACHE_DIR="$CADGEN_TEST_CACHE_DIR"

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "packages/cadgen/src"
