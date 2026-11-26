#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

# The share service (apps/share): no dependencies, so nothing to install first.
section "Share"
npm --prefix apps/share test
