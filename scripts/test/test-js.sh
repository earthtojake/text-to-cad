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

# The optional Hardcore desktop workspace dependency tree is
# large (Electron, Monaco, two native modules) and irrelevant to everyone working
# on cadgen, the viewer or the skills. It is checked when its dependencies are
# installed and skipped, loudly, when they are not -- a contributor who has never
# run `npm ci` is not blocked by a suite they cannot run.
#
# CI does not rely on this: `test.yml`'s `Desktop (macOS)` job installs the
# dependencies itself and runs typecheck, lint, vitest, build and the Playwright
# Electron smoke test. This is the local half.
#
# The e2e is deliberately absent -- it launches a real Electron window, which is
# not something a `test.sh` run should do to whoever is at the keyboard.
if [ -d node_modules/electron-vite ]; then
  section "Hardcore desktop tests"
  npm --prefix apps/desktop run typecheck
  npm --prefix apps/desktop test
else
  section "Hardcore desktop tests (skipped)"
  echo "Desktop workspace dependencies are absent; run 'npm ci' to include them."
fi
