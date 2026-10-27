#!/usr/bin/env bash
set -euo pipefail

# Native file DRC and STEP/mesh round trip with an installed KiCad 9+.
# The runner isolates engine/state/cache directories for each test. No libraries, API server or browser.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cadgen.kicad.install import check_version, find_kicad_cli, kicad_version
cli = find_kicad_cli(); print(f'KiCad {check_version(cli, kicad_version(cli))}: {cli}')" \
  || { echo "test-kicad.sh: KiCad 9 or newer is required for this suite" >&2; exit 1; }

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "packages/cadgen/src"
