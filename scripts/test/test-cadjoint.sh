#!/usr/bin/env bash
set -euo pipefail

# The cadjoint integration: a cadjoint field made a build123d solid (cad.cadjoint.solid), its refusals, a
# field's section drawn, and one model built through an engine of the test's own. The environment is the
# test interpreter's with cad[cadjoint] installed (cadjoint and JAX: some 130 MB from PyPI the first time,
# uv's cache after); Linux only. The package jobs never install it, so requirements-dev.txt does not carry it.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

if ! "$PYTHON_BIN" -c "import cadjoint" 2>/dev/null; then
  echo "test-cadjoint.sh: the suite needs the cadjoint integration's extra in the test interpreter: uv pip install --python .venv --editable \"./packages/cad[cadjoint]\"" >&2
  exit 1
fi

run_python_unittest "cadjoint integration Python tests" "tests/python/packages/cadjoint" "${PACKAGE_SOURCES[@]}"
