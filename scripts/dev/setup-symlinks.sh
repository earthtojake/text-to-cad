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
  scripts/dev/setup-symlinks.sh [--check]

Sets up the development symlink layout by replacing production bundle outputs
with links to their canonical source paths.

Options:
  --check     Verify development symlinks are intact without changing files.
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
  echo "Checking skill development symlinks..."
else
  echo "Setting up skill development symlinks..."
fi
if [ "${#SKILL_ARGS[@]}" -gt 0 ]; then
  "$SCRIPT_DIR/setup-skill-symlink.sh" --all "${SKILL_ARGS[@]}"
else
  "$SCRIPT_DIR/setup-skill-symlink.sh" --all
fi

if [ "$MODE" = "check" ]; then
  echo "Checking plugin development symlinks..."
else
  echo "Setting up plugin development symlinks..."
fi
if [ "${#PLUGIN_ARGS[@]}" -gt 0 ]; then
  "$SCRIPT_DIR/setup-plugin-symlink.sh" "${PLUGIN_ARGS[@]}"
else
  "$SCRIPT_DIR/setup-plugin-symlink.sh"
fi

if [ "$MODE" = "check" ]; then
  echo "Development symlink layout is valid."
else
  echo "Development symlink layout is ready."
fi
