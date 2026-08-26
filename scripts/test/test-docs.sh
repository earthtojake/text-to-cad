#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "Documentation checks"
# Hero GLBs are deliberately NOT LFS (.gitattributes marks docs/public/hero/** with
# !filter), so there is nothing to `git lfs pull` for them -- the old conditional here
# never matched anything.
npm --prefix docs run check
