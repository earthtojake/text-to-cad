#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="write"
SKILL_ARGS=()
PLUGIN_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle.sh [--check] [--clean]

Universal generated-runtime and plugin package bundle wrapper.

Options:
  --check     Bundle into tmp/ and fail if checked-in outputs are stale.
  --clean     Remove temporary bundle/check directories first.
  -h, --help  Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
      SKILL_ARGS+=("--check")
      PLUGIN_ARGS+=("--check")
      ;;
    --clean)
      SKILL_ARGS+=("--clean")
      PLUGIN_ARGS+=("--clean")
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

if [ "$MODE" = "check" ]; then
  echo "Checking derived version metadata..."
  node "$REPO_ROOT/scripts/release/sync-version.mjs" --check
else
  echo "Syncing derived version metadata..."
  node "$REPO_ROOT/scripts/release/sync-version.mjs"
fi

if [ "$MODE" = "check" ]; then
  echo "Checking bundle-capable skill outputs..."
else
  echo "Bundling skill outputs..."
fi
if [ "${#SKILL_ARGS[@]}" -gt 0 ]; then
  "$SCRIPT_DIR/bundle-skill.sh" --all "${SKILL_ARGS[@]}"
else
  "$SCRIPT_DIR/bundle-skill.sh" --all
fi

if [ "$MODE" = "check" ]; then
  echo "Checking plugin package skill copy..."
else
  echo "Bundling plugin package skill copy..."
fi
if [ "${#PLUGIN_ARGS[@]}" -gt 0 ]; then
  "$SCRIPT_DIR/bundle-plugin.sh" "${PLUGIN_ARGS[@]}"
else
  "$SCRIPT_DIR/bundle-plugin.sh"
fi

if [ "$MODE" = "check" ]; then
  echo "All bundle outputs are up to date."
else
  echo "Bundled all production outputs."
fi
