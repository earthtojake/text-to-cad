#!/usr/bin/env bash
set -euo pipefail

# Shared JavaScript suites: @text-to-cad/core, @text-to-cad/ui, the web app, the CAD app and the
# hosted CAD server.
# --select lets a small change run only the affected workspace and its build.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
SELECT=all
while [ "$#" -gt 0 ]; do
  case "$1" in
    --select) SELECT="${2:?--select wants core|ui|web|mcp|cloud|all}"; shift ;;
    --select=*) SELECT="${1#--select=}" ;;
    *) echo "test-js.sh: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done
case "$SELECT" in
  core|ui|web|mcp|cloud|all) ;;
  *) echo "test-js.sh: --select wants core|ui|web|mcp|cloud|all, not '$SELECT'" >&2; exit 2 ;;
esac
cd "$REPO_ROOT"
if [ "$SELECT" = core ]; then
  npm run build --workspace @text-to-cad/core
else
  npm run build:packages
fi
node --test scripts/test/check-dependencies.test.mjs
node scripts/test/check-dependencies.mjs
node --test scripts/test/check-kit-boundaries.test.mjs
node scripts/test/check-kit-boundaries.mjs
if [ "$SELECT" = core ] || [ "$SELECT" = all ]; then
  section "@text-to-cad/core tests"
  npm --prefix packages/core test
  section "viewer benchmark helper tests"
  node --test scripts/bench/viewer-memory/*.test.mjs
fi
if [ "$SELECT" = ui ] || [ "$SELECT" = all ]; then
  section "@text-to-cad/ui tests"
  npm --prefix packages/ui test
fi
if [ "$SELECT" = web ] || [ "$SELECT" = all ]; then
  section "CAD Viewer tests"
  npm --prefix apps/web run test
fi
if [ "$SELECT" = mcp ] || [ "$SELECT" = all ]; then
  section "CAD app tests"
  npm --prefix apps/mcp run test
  # The build is the other half of the contract: one index.html with nothing outside it.
  npm --prefix apps/mcp run build
fi
if [ "$SELECT" = cloud ] || [ "$SELECT" = all ]; then
  section "hosted CAD server tests"
  npm --prefix apps/cloud run typecheck
  npm --prefix apps/cloud run typecheck:server
  # The viewer page is built first: the browser test draws a real export on it.
  npm --prefix apps/cloud run build
  npm --prefix apps/cloud test
fi
