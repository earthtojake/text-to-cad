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
projects (cad and its three aliases) are that version and require cad at it
(`cad==<version>`), that it is not one PyPI will never take
(scripts/release/unavailable-versions.txt), that every plugin manifest names it,
that Codex's server
line runs it (`cad@<version> mcp`) and that each skill names it as the cad it was
written for (`cad==<version>`), with no command pinned to a version. main is the
source branch AND what installers clone, so a stale version ships.
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

# The four projects' versions (cad and its aliases) and every release a file names (`cad==X`, `cad@X`) must be THIS
# version. The release PR stamps them (sync-version.mjs) alongside VERSION; another version means the two moved
# separately.
stale=0
# cad as a requirement (`cad==X`, with an extra or not) or as uvx runs it (`cad@X`), standing alone (`my-cad==` and
# `text-to-cad@earthtojake` are other names), at a version. grep -o keeps the character before the name, which `pins`
# takes off.
PIN='(^|[^[:alnum:]_.-])cad(\[[a-z0-9_,.-]+\])?(==|@)[0-9][^[:space:]`"'"'"')]*'
pins() { grep -rhoE --include='*.md' --include='*.toml' --include='*.json' -- "$PIN" "$@" | sed -E 's/^[^c]//' || true; }
check_pins() {  # where, then the pins found there: each must name $version
  local where="$1" pin
  while IFS= read -r pin; do
    [ -n "$pin" ] || continue
    if [ "$(printf '%s' "$pin" | sed -E 's/^[^=@]*(==|@)//')" != "$version" ]; then
      echo "$where names $pin; expected $version" >&2
      stale=1
    fi
  done <<< "$2"
}
for project in packages/cad packages/aliases/*; do
  declared="$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project/pyproject.toml")"
  if [ "$declared" != "$version" ]; then
    echo "$project/pyproject.toml is ${declared:-unversioned}; expected $version" >&2
    stale=1
  fi
  check_pins "$project/pyproject.toml" "$(pins "$project/pyproject.toml")"
done
# Every plugin manifest says the release it is (each `"version"` field, a catalog's plugin entries
# too), and the one server config, Codex's, starts that release's server (`cad@<version> mcp`).
for manifest in .claude-plugin/plugin.json .claude-plugin/marketplace.json .codex-plugin/plugin.json \
    .cursor-plugin/plugin.json .grok-plugin/plugin.json .antigravity-plugin/plugin.json \
    .kimi-plugin/plugin.json .devin-plugin/plugin.json .muse-plugin/plugin.json .muse-plugin/marketplace.json \
    gemini-extension.json; do
  declared="$(grep -oE '"version": *"[^"]*"' "$manifest" | sed -E 's/.*"([^"]*)"$/\1/' | sort -u)"
  if [ "$declared" != "$version" ]; then
    echo "$manifest names version ${declared:-(none)}; expected $version" >&2
    stale=1
  fi
done
configured="$(pins codex.mcp.json)"
if ! printf '%s\n' "$configured" | grep -q '^cad@'; then
  echo "codex.mcp.json starts no server of a release (cad@$version mcp)" >&2
  stale=1
fi
check_pins codex.mcp.json "$configured"
# Each skill's setup block names the cad it was written for (`cad==<version>`); no command names a version.
if [ -d skills ]; then
  written_for="$(pins skills)"
  if ! printf '%s\n' "$written_for" | grep -q '^cad=='; then
    echo "no skill names the cad it was written for (cad==$version)" >&2
    stale=1
  fi
  check_pins skills/ "$(printf '%s\n' "$written_for" | sort -u)"
  if grep -rlE --include='*.md' -- '(^|[^[:alnum:]_.-])cad(\.exe)? \+' skills >&2; then
    echo "the files above run a command pinned to a version (cad +<version>); commands are plain cad" >&2
    stale=1
  fi
fi
if [ "$stale" -ne 0 ]; then
  echo "Run node scripts/release/sync-version.mjs to stamp the pins from VERSION." >&2
  exit 1
fi
echo "The four projects, the plugin manifests, Codex's server line and the skills match VERSION ($version)."
