#!/usr/bin/env bash
set -euo pipefail

# The packages' floor: the library's suite, the server's and the shim's, on the oldest Python the packages declare
# (requires-python in packages/cad/pyproject.toml). Our own installs run cad on a newer one
# (cad_server._internal.launch.PYTHON), and so does every other job. But pip, pipx or a plain `uv tool install cad`
# on a system Python puts cad on whatever Python meets the floor. A call the floor's standard library lacks parses
# there and fails only when it runs (one already slipped into the server: argparse's suggest_on_error), so nothing
# but running the suites on it holds the floor.
#
#   uv sync --python 3.11 && uv run scripts/test/test-floor.sh
#
# (or PYTHON_BIN naming another Python of the floor with the development environment installed). Called by
# test.yml's packages-floor job, on a full run (before a release ships, and nightly), which makes the environment
# on the floor first. A checkout's .venv stays on 3.11 until `uv sync --python 3.14` puts it back. On Linux it draws stills: run it under xvfb-run, as the package suites are.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

floor="$(sed -n 's/^requires-python = ">=\([0-9][0-9.]*\)"$/\1/p' packages/cad/pyproject.toml)"
have="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ -z "$floor" ] || [ "$have" != "$floor" ]; then
  echo "test-floor.sh: $PYTHON_BIN is Python $have, and the packages' floor is ${floor:-unread}: set PYTHON_BIN to" \
    "a Python $floor with the development environment installed (uv sync --python $floor)" >&2
  exit 1
fi

run_python_unittest "cad (the library) Python tests, on Python $floor" "tests/python/packages/cad" "${PACKAGE_SOURCES[@]}"
run_python_unittest "cad-server Python tests, on Python $floor" "tests/python/packages/cad_server" "${PACKAGE_SOURCES[@]}"
run_python_unittest "cad-mcp (the shim) Python tests, on Python $floor" "tests/python/packages/cad_mcp" "${PACKAGE_SOURCES[@]}"
