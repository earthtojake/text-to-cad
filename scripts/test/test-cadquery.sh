#!/usr/bin/env bash
set -euo pipefail

# CadQuery handed over to the engine, where the `cad` command runs it: in the environment of the cadquery
# integration, cad[cadquery], which the server makes (the library from this checkout, editable, and CadQuery
# on its own OCP build, 7.9: some 300 MB from PyPI the first time, uv's cache after). A Workplane and an
# Assembly handed over from a CadQuery program to this run's engine (the kernel, OCP 8.0), served and exported,
# and `cad run` choosing the integration from the script's import. The environment is made once here, in
# folders of this run's own (no engine of the person's is asked to make it), and named to the tests
# (CAD_TEST_CADQUERY_PYTHON); the runner gives each test file its own engine, state and cache folders.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

scratch="$REPO_ROOT/tmp/cadquery-suite"
mkdir -p "$scratch"
CAD_TEST_CADQUERY_PYTHON="$(
  CAD_CACHE_DIR="$scratch/cache" CAD_STATE_DIR="$scratch/state" CAD_ENGINE_DIR="$scratch/engine" \
    PYTHONPATH="$(IFS=:; echo "${PACKAGE_SOURCES[*]}")${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
    "import sys
from cad_server._internal import integration_env
python = integration_env.environment('cadquery', lambda line: print(line, file=sys.stderr))
print(python)"
)" || { echo "test-cadquery.sh: the environment of cad[cadquery] could not be made" >&2; exit 1; }
"$CAD_TEST_CADQUERY_PYTHON" -c "import cadquery, importlib.metadata as m; print(f'cadquery {cadquery.__version__} on cadquery-ocp {m.version(\"cadquery-ocp\")}')"
export CAD_TEST_CADQUERY_PYTHON

run_python_unittest "CadQuery Python tests" "tests/python/packages/cadquery" "${PACKAGE_SOURCES[@]}"
