#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

section "cadgen-js tests"
npm --prefix packages/cadgen-js test

section "CAD Viewer tests"
npm --prefix apps/viewer run test

# The Hardcore desktop app is a standalone npm project whose dependency tree is
# large (Electron, Monaco, two native modules) and irrelevant to everyone working
# on cadgen, the viewer or the skills. It is checked when its dependencies are
# installed and skipped, loudly, when they are not -- a contributor who has never
# run `npm --prefix apps/desktop ci` is not blocked by a suite they cannot run.
#
# CI does not rely on this: `test.yml`'s `Desktop (macOS)` job installs the
# dependencies itself and runs typecheck, lint, vitest, build and the Playwright
# Electron smoke test. This is the local half.
#
# The e2e is deliberately absent -- it launches a real Electron window, which is
# not something a `test.sh` run should do to whoever is at the keyboard.
if [ -d apps/desktop/node_modules ]; then
  section "Hardcore desktop tests"
  npm --prefix apps/desktop run typecheck
  npm --prefix apps/desktop test
else
  section "Hardcore desktop tests (skipped)"
  echo "apps/desktop/node_modules is absent; run 'npm --prefix apps/desktop ci' to include them."
fi
