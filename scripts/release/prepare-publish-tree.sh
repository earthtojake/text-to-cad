#!/usr/bin/env bash
set -euo pipefail

# Shape a source checkout into the tree that `main` carries.
#
# `main` is `develop` with versions stamped (scripts/release/sync-version.mjs),
# skill requirements pinned (scripts/release/pin-cadgen-requirements.sh), and ONLY
# `models/` removed. Nothing else is trimmed: apps/, packages/, tests/ and
# requirements-dev.txt ship, so the source behind every release is discoverable on
# the default branch. That tree is ~15 MB with no LFS objects; models/ is the
# fixture corpus and the only thing whose absence buys anything. No skill carries
# a generated runtime (the CAD Viewer ships inside the cadgen wheel), and the
# repository has no development symlinks left to dereference.
#
# This script removes the roots in REMOVED_ROOTS (models/). It is a PUBLISH-TREE
# transformation, run by the Release workflow after bundle.sh --clean and every
# check, before pin-cadgen-requirements.sh and the publish commit. It never runs
# on a development checkout: it deletes models/.
# scripts/github-workflows/check-publish-tree.sh verifies the result.
#
# Usage:
#   scripts/release/prepare-publish-tree.sh
#   scripts/release/prepare-publish-tree.sh --print-removed-roots

REPO_ROOT="${PUBLISH_TREE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# The single source of truth for what the publish tree drops. The Release
# workflow reads it (--print-removed-roots) to assert the roots are absent from
# the publish commit and to stop demanding generated outputs under them.
REMOVED_ROOTS=(models)

usage() {
  cat <<'EOF'
Usage:
  scripts/release/prepare-publish-tree.sh
  scripts/release/prepare-publish-tree.sh --print-removed-roots

Turns a checkout into the publish tree: removes models/. Run only in the Release
workflow (or a scratch worktree) -- never on a development checkout.
EOF
}

case "${1:-}" in
  "") ;;
  --print-removed-roots)
    printf '%s\n' "${REMOVED_ROOTS[@]}"
    exit 0
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown argument: $1" >&2
    usage >&2
    exit 2
    ;;
esac

cd "$REPO_ROOT"

for root in "${REMOVED_ROOTS[@]}"; do
  rm -rf "$root"
  if [ -e "$root" ] || [ -L "$root" ]; then
    echo "Failed to remove $root from the publish tree." >&2
    exit 1
  fi
  echo "Removed $root/"
done

echo "Publish tree prepared: removed ${REMOVED_ROOTS[*]}."
