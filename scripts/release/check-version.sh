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
(scripts/release/unavailable-versions.txt), that the one-line installer's
scripts fall back to it, that every plugin manifest names it and every server config
and skill command pins it (`cad-mcp==<version>`, `cad +<version>`). main is the source branch AND what
installers clone, so a stale pin ships.
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

# The four distributions' versions and their pins of the library must name THIS version. The release
# PR stamps them (sync-version.mjs) alongside VERSION; another version means the two moved separately.
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
# The one-line installer falls back to the release it was published with.
fallback="$(sed -n 's/^FALLBACK = "\([^"]*\)"$/\1/p' scripts/install/install.py)"
if [ "$fallback" != "$version" ]; then
  echo "scripts/install/install.py falls back to ${fallback:-(no stamped version)}; expected $version" >&2
  stale=1
fi
# Every plugin manifest says the release it is (each `"version"` field, a catalog's plugin entries
# too), and every server config starts that release's server (`cad-mcp==<version>`).
for manifest in .claude-plugin/plugin.json .claude-plugin/marketplace.json .codex-plugin/plugin.json \
    .cursor-plugin/plugin.json .grok-plugin/plugin.json .antigravity-plugin/plugin.json \
    .kimi-plugin/plugin.json .devin-plugin/plugin.json .muse-plugin/plugin.json .muse-plugin/marketplace.json \
    gemini-extension.json plugin.json; do
  declared="$(grep -oE '"version": *"[^"]*"' "$manifest" | sed -E 's/.*"([^"]*)"$/\1/' | sort -u)"
  if [ "$declared" != "$version" ]; then
    echo "$manifest names version ${declared:-(none)}; expected $version" >&2
    stale=1
  fi
done
for config in codex.mcp.json grok.mcp.json cursor.mcp.json mcp.json gemini-extension.json \
    .kimi-plugin/plugin.json .devin-plugin/plugin.json; do
  configured="$(pins "$config")"
  if [ -z "$configured" ]; then
    echo "$config starts no pinned server (cad-mcp==$version)" >&2
    stale=1
  fi
  while IFS= read -r pin; do
    [ -n "$pin" ] || continue
    if [ "${pin##*==}" != "$version" ]; then
      echo "$config pins $pin; expected ${pin%%==*}==$version" >&2
      stale=1
    fi
  done <<< "$configured"
done
# Every command a skill runs pins its release, `cad +<version> <verb>`, and the setup block installs it,
# `--from cad-server==<version>`: the skill text of a release runs that release.
if [ -d skills ]; then
  RELEASE='[0-9]+\.[0-9]+\.[0-9]+([0-9A-Za-z.+_-]*[0-9A-Za-z])?'
  skill_pins="$(grep -rhoE --include='*.md' -- "(^|[^[:alnum:]_.-])cad \\+$RELEASE|(^|[^[:alnum:]_.-])cad-server==$RELEASE" skills |
    sed -E 's/^[^c]//' || true)"
  if ! printf '%s\n' "$skill_pins" | grep -q '^cad +'; then
    echo "no skill pins its commands (cad +$version)" >&2
    stale=1
  fi
  while IFS= read -r pin; do
    [ -n "$pin" ] || continue
    if [ "${pin##* +}" != "$version" ] && [ "${pin##*==}" != "$version" ]; then
      echo "skills/ pins $pin; expected $version" >&2
      stale=1
    fi
  done < <(printf '%s\n' "$skill_pins" | sort -u)
fi
if [ "$stale" -ne 0 ]; then
  echo "Run node scripts/release/sync-version.mjs to stamp the pins from VERSION." >&2
  exit 1
fi
echo "The four distributions, their pins, the installer's fallback, the plugin manifests and the skills' pins match VERSION ($version)."
