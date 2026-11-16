#!/usr/bin/env bash
set -euo pipefail

# Native KiCad boards with kicode's kicad-cli and KiPy, where the `cad` command runs them: in the
# environment of the kicad integration, cad[kicad], which the server makes (the library from this
# checkout, editable, and kicode: some 100 MB from PyPI the first time, uv's cache after). DRC, every
# export, a STEP and mesh round trip, a schematic's ERC, exports and nets held to KiCad's netlist, a
# board's and a schematic's edit (kicad_pcb.edit, kicad_sch.edit) through the headless api-server, and a
# plan routed inside a board's edit (cad.kicad.route) and judged by DRC.
# The environment is made once here, in folders of this run's own (no engine of the person's is asked
# to make it), and named to the tests (CAD_TEST_KICODE_PYTHON); the runner gives each test file its own
# engine, state and cache folders. No person's KiCad, no libraries, no browser.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

scratch="$REPO_ROOT/tmp/kicad-suite"
mkdir -p "$scratch"
CAD_TEST_KICODE_PYTHON="$(
  CAD_CACHE_DIR="$scratch/cache" CAD_STATE_DIR="$scratch/state" CAD_ENGINE_DIR="$scratch/engine" \
    PYTHONPATH="$(IFS=:; echo "${PACKAGE_SOURCES[*]}")${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
    "import sys
from cad_server._internal import integration_env
python = integration_env.environment('kicad', lambda line: print(line, file=sys.stderr))
print(python)"
)" || { echo "test-kicad.sh: the environment of cad[kicad] could not be made" >&2; exit 1; }
"$CAD_TEST_KICODE_PYTHON" -c "import kicode; print(f'kicode {kicode.KICAD_VERSION} ({kicode.KICAD_COMMIT[:9]}): {kicode.executable()}')"
export CAD_TEST_KICODE_PYTHON
# The engines the suite starts refill a board's pours with KiCad, as a person's do (the runner's default is off).
export CAD_KICAD_REFILL=1

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "${PACKAGE_SOURCES[@]}"
