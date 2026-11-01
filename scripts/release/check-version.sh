#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=release-tags.sh
source "$SCRIPT_DIR/release-tags.sh"

usage() {
  cat <<'EOF'
Usage:
  scripts/release/check-version.sh [--incremented-from REF]

Checks that VERSION contains a valid canonical release version, that the four
distributions (the library, the server, the shim and the alias) are that
version and pin each other at it (`cad==<version>`), that it is not one PyPI will never take
(scripts/release/unavailable-versions.txt), that every skill's
SKILL.md and setup guide (references/setup.md) name exactly that version: its
install command (`uvx ... --from cad-server==<version> cad doctor`) and the
version it runs (`cad +<version>`, "it says <version> is not installed"), and
that the one-line installer's scripts fall back to it. main is the source
branch AND what installers clone, so a stale pin ships.
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
refuse_unavailable_version "$version" || exit 1
echo "Canonical release version is valid: $version"
if [ -n "$BASE_REF" ]; then
  "$SCRIPT_DIR/bump-version.sh" --check-incremented-from "$BASE_REF"
fi

# Every skill's install command and `cad +<version>` must name THIS version, and so must the four
# distributions' versions and their pins of the library. The release PR stamps them (sync-version.mjs)
# alongside VERSION; another version means the two moved separately.
stale=0
# A pin names the library (`cad`, with an extra or not), the server or the shim, standing alone: `cad` at
# the end of another name (`my-cad==`) is none of them. grep -o keeps the character before the name,
# which `pins` takes off.
PIN='(^|[^[:alnum:]_.-])cad(-server|-mcp)?(\[[a-z0-9_,.-]+\])?==[^[:space:]`"'"'"']+'
pins() { grep -oE -- "$PIN" "$1" | sed -E 's/^[^c]//' || true; }
for project in packages/cad packages/cad-server packages/cad-mcp packages/aliases/cadgen; do
  declared="$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project/pyproject.toml")"
  if [ "$declared" != "$version" ]; then
    echo "$project/pyproject.toml is ${declared:-unversioned}; expected $version" >&2
    stale=1
  fi
  while IFS= read -r pin; do
    if [ "${pin##*==}" != "$version" ]; then
      echo "$project/pyproject.toml pins $pin; expected ${pin%%==*}==$version" >&2
      stale=1
    fi
  done < <(pins "$project/pyproject.toml")
done
while IFS= read -r skill; do
  while IFS= read -r pin; do
    if [ "${pin##*==}" != "$version" ]; then
      echo "$skill pins $pin; expected ${pin%%==*}==$version" >&2
      stale=1
    fi
  done < <(pins "$skill")
  while IFS= read -r named; do
    if [ "$named" != "$version" ]; then
      echo "$skill runs cad +$named; expected +$version" >&2
      stale=1
    fi
  done < <(grep -oE -- '(\bcad(\.cmd)? \+|it says )[0-9][^[:space:]`)]*' "$skill" | sed -E 's/^(cad(\.cmd)? \+|it says )//')
done < <(find skills -mindepth 2 -maxdepth 3 -type f \( -name SKILL.md -o -path '*/references/setup.md' \) | sort)
# The one-line installer falls back to the release it was published with.
for script in scripts/install/install.sh scripts/install/install.ps1; do
  fallback="$(sed -n -e 's/^CAD_VERSION="\([^"]*\)"$/\1/p' -e 's/^[[:space:]]*\$CadVersion = "\([^"]*\)"$/\1/p' "$script")"
  if [ "$fallback" != "$version" ]; then
    echo "$script falls back to ${fallback:-(no stamped version)}; expected $version" >&2
    stale=1
  fi
done
if [ "$stale" -ne 0 ]; then
  echo "Run node scripts/release/sync-version.mjs to stamp the pins from VERSION." >&2
  exit 1
fi
echo "The four distributions, their pins, the skills' pins and versions and the installer's fallback match VERSION ($version)."
