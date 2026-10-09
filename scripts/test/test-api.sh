#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

# api.texttocad.dev: no dependencies, so nothing to install first.
section "API"
npm --prefix apps/api test
