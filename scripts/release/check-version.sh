#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/release/check-version.sh [--incremented-from REF]

Checks that VERSION contains a valid canonical release version and that every
skill's launch command (`uvx ... --from cadgen==<version>` in its SKILL.md) pins
exactly that version (main is the source branch AND what installers clone, so a
stale pin ships).
With --incremented-from, also checks that the current version is greater than
the version at REF (a commit, branch, or release tag -- `v0.5.0` or the bare
`0.4.28` spelling releases before 0.5.0 used; the VERSION file at that commit
is what is compared, so the tag's spelling does not matter).

Options:
  --incremented-from REF  Compare current release version against REF.
  -h, --help              Show this help.
EOF
}

BASE_REF=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --incremented-from)
      [ "$#" -ge 2 ] || {
        echo "--incremented-from requires a ref" >&2
        exit 2
      }
      BASE_REF="$2"
      shift
      ;;
    --incremented-from=*)
      BASE_REF="${1#--incremented-from=}"
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
  shift
done

cd "$REPO_ROOT"

version="$(tr -d '[:space:]' < VERSION)"
if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "VERSION must be a plain semver version like 1.2.3, got '$version'" >&2
  exit 1
fi
echo "Canonical release version is valid: $version"
if [ -n "$BASE_REF" ]; then
  "$SCRIPT_DIR/bump-version.sh" --check-incremented-from "$BASE_REF"
fi

# Every skill's launch command must pin THIS version. The release PR stamps the
# pins (sync-version.mjs) alongside VERSION; a pin at another version means the two
# moved separately.
stale=0
while IFS= read -r skill; do
  while IFS= read -r pin; do
    if [ "$pin" != "$version" ]; then
      echo "$skill pins cadgen==$pin; expected cadgen==$version" >&2
      stale=1
    fi
  done < <(grep -oE -- '--from cadgen==[^[:space:]`]+' "$skill" | sed 's/.*==//')
done < <(find skills -mindepth 2 -maxdepth 2 -name SKILL.md -type f | sort)
if [ "$stale" -ne 0 ]; then
  echo "Run node scripts/release/sync-version.mjs to stamp the pins from VERSION." >&2
  exit 1
fi
echo "Skill cadgen pins match VERSION ($version)."
