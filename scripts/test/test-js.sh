#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "@hardcore/core tests"
npm run build:packages

node --test scripts/test/check-dependencies.test.mjs
node scripts/test/check-dependencies.mjs
npm --prefix packages/core test
npm --prefix packages/ui test

section "CAD Viewer tests"
npm --prefix apps/web run test

# The viewer-memory benchmark drivers are manual, but the pure helpers they are
# built from (grading, completion, fingerprints, probes) are ordinary units with
# no browser and no platform dependency, so they run with the rest of the suite.
section "viewer benchmark helper tests"
node --test scripts/bench/viewer-memory/*.test.mjs
