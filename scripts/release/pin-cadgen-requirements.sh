#!/usr/bin/env bash
set -euo pipefail

# Stamp every skill's cadgen requirement to `cadgen==<VERSION>`.
#
# main is the source branch and what installers clone, so the pins live IN the
# tree: the release PR runs this beside bump-version.sh and sync-version.mjs, and
# scripts/release/check-version.sh asserts every pin equals VERSION from then
# on. A developer's editable install of packages/cadgen reports VERSION too
# (sync-version stamps pyproject.toml), so `cadgen==X` is satisfied in a checkout
# without touching PyPI -- install requirements-dev.txt, not a skill's
# requirements.txt, which would fetch the previous release from PyPI instead.
#
# A bare `cadgen` / `cadgen[extras]` line is rewritten; an existing `==` pin at
# another version is rewritten too, so a bump moves every pin at once.
#
# Usage: scripts/release/pin-cadgen-requirements.sh [--check]
#   --check  report what would change and exit 1 if anything would, without writing.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
elif [ -n "${1:-}" ]; then
  echo "usage: scripts/release/pin-cadgen-requirements.sh [--check]" >&2
  exit 2
fi

version="$(tr -d '[:space:]' < VERSION)"
if [ -z "$version" ]; then
  echo "Missing canonical release version: VERSION" >&2
  exit 1
fi

# A skill names the DISTRIBUTION, optionally with extras (`cadgen[snapshot]`), either
# bare or pinned to some version. Both spellings are rewritten to this VERSION.
DIST_RE='^cadgen(\[[a-z0-9_,-]+\])?[[:space:]]*(==[[:space:]]*[^[:space:]#;]+)?[[:space:]]*$'

pending=0
while IFS= read -r manifest; do
  if ! grep -Eq "$DIST_RE" "$manifest"; then
    continue
  fi
  if grep -Eq "^cadgen(\[[a-z0-9_,-]+\])?[[:space:]]*==[[:space:]]*$version[[:space:]]*$" "$manifest"; then
    continue  # already at this version
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "would pin: $manifest -> cadgen==$version"
    pending=1
    continue
  fi
  sed -E -i.bak -e "s|$DIST_RE|cadgen\1==$version|" "$manifest"
  rm -f "$manifest.bak"
  echo "pinned: $manifest -> cadgen==$version"
done < <(
  find . \
    \( -name node_modules -o -name .git -o -name .venv -o -name tmp -o -name models \) -prune -o \
    -name requirements.txt -type f -print | sort
)

if [ "$CHECK_ONLY" -eq 1 ] && [ "$pending" -ne 0 ]; then
  echo "cadgen requirements are not pinned to $version." >&2
  exit 1
fi
