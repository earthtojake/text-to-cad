#!/usr/bin/env bash
set -euo pipefail

# Native KiCad file commands with an installed KiCad 9+: DRC, a STEP and mesh round trip, a schematic's
# ERC, exports and nets held to KiCad's netlist, and (on a nightly, with the kicad extra) a @kicad_pcb
# board script through the headless api-server.
# The runner gives each test file its own engine, state and cache folders. No libraries or
# server or browser. KiCad is found as `cad kicad_pcb check` finds it (CAD_KICAD_CLI, else PATH).

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$(IFS=:; echo "${PACKAGE_SOURCES[*]}")${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cad.kicad._program import check_version, find_kicad_cli, kicad_version
cli = find_kicad_cli(); print(f'KiCad {check_version(cli, kicad_version(cli))}: {cli}')" \
  || { echo "test-kicad.sh: KiCad 9 or newer is required for this suite" >&2; exit 1; }

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "${PACKAGE_SOURCES[@]}"
