#!/usr/bin/env bash
set -euo pipefail

# The packages' floor: the library's suite, the server's and the shim's, on the oldest Python the packages declare
# (requires-python in packages/cad/pyproject.toml). The server's installations run on a newer one
# (cad_server._internal.launch.PYTHON), and so does every other job; the library runs on the floor wherever a
# render script does (bpy has builds for that Python alone: cad[blender]), in the script's process and in the
# worker that builds its models, and the server and the shim declare the same floor, so a pip install puts them
# on it too. A call the floor's standard library lacks parses there and fails only when it runs (one already
# slipped into the server: argparse's suggest_on_error), so nothing but running the suites on it holds the floor.
#
#   PYTHON_BIN=<a Python of the floor, requirements-dev.txt installed> scripts/test/test-floor.sh
#
# Called by test.yml's packages-floor job, on a full run (before a release ships, and nightly), which makes the
# environment first. On Linux it draws stills: run it under xvfb-run, as the package suites are.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

floor="$(sed -n 's/^requires-python = ">=\([0-9][0-9.]*\)"$/\1/p' packages/cad/pyproject.toml)"
have="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ -z "$floor" ] || [ "$have" != "$floor" ]; then
  echo "test-floor.sh: $PYTHON_BIN is Python $have, and the packages' floor is ${floor:-unread}: set PYTHON_BIN to" \
    "a Python $floor with requirements-dev.txt installed" >&2
  exit 1
fi

run_python_unittest "cad (the library) Python tests, on Python $floor" "tests/python/packages/cad" "${PACKAGE_SOURCES[@]}"
run_python_unittest "cad-server Python tests, on Python $floor" "tests/python/packages/cad_server" "${PACKAGE_SOURCES[@]}"
run_python_unittest "cad-mcp (the shim) Python tests, on Python $floor" "tests/python/packages/cad_mcp" "${PACKAGE_SOURCES[@]}"
