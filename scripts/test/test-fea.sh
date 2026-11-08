#!/usr/bin/env bash
set -euo pipefail

# The stress study (cad <type> solve) and its result (cad fea) with their integrations installed: netgen, the
# netgen integration's (cad[netgen]), meshes, and CalculiX's ccx, the calculix integration's (cad[calculix]: the
# ccx package), solves. The suite's own folder, tests/python/packages/fea, is this job's alone: the package jobs
# install neither. The study's parse, checks and materials run in seconds; the solves against hand calculations
# are most of its time. The command runs a study here when this Python holds the kernel, netgen and ccx, else
# through the library's runner of one operation in the environment of cad[build123d,calculix,netgen]; the suite
# runs that path with this Python standing in for that environment (test_fea_commands.py). The runner gives each
# test file its own engine, state and cache folders. No browser, and never a ccx of the person's.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

"$PYTHON_BIN" -c "import netgen.meshing" || { echo "test-fea.sh: netgen is not installed: install ./packages/cad[netgen]" >&2; exit 1; }
"$PYTHON_BIN" -c "import ccx; ccx.executable()" || { echo "test-fea.sh: the ccx package is not installed: install ./packages/cad[calculix]" >&2; exit 1; }

run_python_unittest "Stress study (solve, fea) Python tests" "tests/python/packages/fea" "${PACKAGE_SOURCES[@]}"
