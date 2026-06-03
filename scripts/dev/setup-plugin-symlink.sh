#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"
UTILS_SCRIPT="$SCRIPT_DIR/symlink-utils.sh"

MODE="write"

usage() {
  cat <<'EOF'
Usage:
  scripts/dev/setup-plugin-symlink.sh [--check]

Sets up plugins/cad/skills as symlinks to root skills/* for development.

Options:
  --check     Verify plugin development symlinks are intact without changing files.
  -h, --help  Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
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

if [ ! -x "$LIST_SKILLS_SCRIPT" ]; then
  echo "Missing skill list script: $LIST_SKILLS_SCRIPT" >&2
  exit 1
fi

# shellcheck source=scripts/dev/symlink-utils.sh
source "$UTILS_SCRIPT"

cd "$REPO_ROOT"
if [ "$MODE" != "check" ]; then
  mkdir -p "plugins/cad/skills"
fi

while IFS= read -r skill; do
  setup_link "$MODE" "plugins/cad/skills/$skill" "../../../skills/$skill"
done < <("$LIST_SKILLS_SCRIPT")
