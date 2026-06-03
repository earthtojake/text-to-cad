#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "cadjs tests"
npm --prefix packages/cadjs test

section "implicitjs tests"
npm --prefix packages/implicitjs test

section "CAD Viewer tests"
npm --prefix viewer run test
