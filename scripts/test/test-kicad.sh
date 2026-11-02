#!/usr/bin/env bash
set -euo pipefail

# Native KiCad file commands with an installed KiCad 9+: DRC, and a STEP and mesh round trip.
# The runner gives each test file its own engine, state and cache folders. No libraries, API
# server or browser. KiCad is found as `cad kicad_pcb check` finds it (CAD_KICAD_CLI, else PATH).

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$(IFS=:; echo "${PACKAGE_SOURCES[*]}")${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cad_server.kicad.install import check_version, find_kicad_cli, kicad_version
cli = find_kicad_cli(); print(f'KiCad {check_version(cli, kicad_version(cli))}: {cli}')" \
  || { echo "test-kicad.sh: KiCad 9 or newer is required for this suite" >&2; exit 1; }

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "${PACKAGE_SOURCES[@]}"
