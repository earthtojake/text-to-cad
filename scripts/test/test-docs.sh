#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "Documentation checks"
# Static skill links are a contract even when skill prose skips the site build.
"$PYTHON_BIN" -m unittest tests/python/global/test_plugin_manifests.py
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git lfs version >/dev/null 2>&1; then
  if git lfs ls-files --name-only | grep -q '^apps/docs/public/hero/'; then
    git lfs pull --include="apps/docs/public/hero/**" --exclude=""
  fi
fi
npm --prefix apps/docs run check
