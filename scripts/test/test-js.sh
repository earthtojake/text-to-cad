#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "cadgen-js tests"
npm --prefix packages/cadgen-js test

section "CAD Viewer tests"
npm --prefix apps/viewer run test

# The viewer-memory benchmark drivers are manual, but the pure helpers they are
# built from (grading, completion, fingerprints, probes) are ordinary units with
# no browser and no platform dependency, so they run with the rest of the suite.
section "viewer benchmark helper tests"
node --test scripts/bench/viewer-memory/*.test.mjs
