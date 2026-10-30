#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/release/check-version.sh [--incremented-from REF]

Checks that VERSION contains a valid canonical release version, that every
skill's SKILL.md and setup guide (references/setup.md) name exactly that
version: its install command (`uvx ... --from cadgen==<version> cadgen doctor`)
and the version it runs (`cadgen +<version>`, "it says <version> is not
installed"), and that the one-line installer's scripts fall back to it. main is
the source branch AND what installers clone, so a stale pin ships.
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

# Every skill's install command and `cadgen +<version>` must name THIS version. The release PR
# stamps them (sync-version.mjs) alongside VERSION; another version means the two
# moved separately.
stale=0
while IFS= read -r skill; do
  while IFS= read -r pin; do
    if [ "$pin" != "$version" ]; then
      echo "$skill pins cadgen==$pin; expected cadgen==$version" >&2
      stale=1
    fi
  done < <(grep -oE -- 'cadgen==[^[:space:]`"'"'"']+' "$skill" | sed 's/.*==//')
  while IFS= read -r named; do
    if [ "$named" != "$version" ]; then
      echo "$skill runs cadgen +$named; expected +$version" >&2
      stale=1
    fi
  done < <(grep -oE -- '(cadgen(\.cmd)? \+|it says )[0-9][^[:space:]`)]*' "$skill" | sed -E 's/^(cadgen(\.cmd)? \+|it says )//')
done < <(find skills -mindepth 2 -maxdepth 3 -type f \( -name SKILL.md -o -path '*/references/setup.md' \) | sort)
# The one-line installer falls back to the release it was published with.
for script in scripts/install/install.sh scripts/install/install.ps1; do
  fallback="$(sed -n -e 's/^CADGEN_VERSION="\([^"]*\)"$/\1/p' -e 's/^[[:space:]]*\$CadgenVersion = "\([^"]*\)"$/\1/p' "$script")"
  if [ "$fallback" != "$version" ]; then
    echo "$script falls back to cadgen ${fallback:-(no stamped version)}; expected $version" >&2
    stale=1
  fi
done
if [ "$stale" -ne 0 ]; then
  echo "Run node scripts/release/sync-version.mjs to stamp the pins from VERSION." >&2
  exit 1
fi
echo "Skill cadgen pins, versions and the installer's fallback match VERSION ($version)."
