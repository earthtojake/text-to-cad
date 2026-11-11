#!/usr/bin/env bash
set -euo pipefail

# The router's unit files (tests/python/packages/cad/test_kicad_routing*.py: cad.kicad.route's core, no
# KiCad), on whatever OS runs this. The packages jobs run them on Linux and Windows with the rest of the
# library's suite; CI runs this on macOS, whose C library (Apple's libm) is the third the router's copper
# must not depend on: test_kicad_routing_determinism.py holds one board's copper to a digest on all three.
# They need the library alone (numpy; no CAD kernel, no KiCad).

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

for file in tests/python/packages/cad/test_kicad_routing*.py; do
  TEST_PATHS+=("$file")
done

run_python_unittest "the router's unit files" "tests/python/packages/cad" "${PACKAGE_SOURCES[@]}"
require_selected_tests
