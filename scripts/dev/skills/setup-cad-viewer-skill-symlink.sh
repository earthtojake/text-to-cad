#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
UTILS_SCRIPT="$REPO_ROOT/scripts/dev/symlink-utils.sh"

MODE="write"

usage() {
  cat <<'EOF'
Usage:
  scripts/dev/setup-skill-symlink.sh cad-viewer [--check]

Sets up CAD Viewer development symlinks.

Options:
  --check     Verify symlinks are intact without changing files.
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

# shellcheck source=scripts/dev/symlink-utils.sh
source "$UTILS_SCRIPT"

check_no_tracked_runtime_dist() {
  local tracked_dist
  tracked_dist="$(
    git ls-files \
      "skills/cad-viewer/scripts/viewer/dist" \
      "skills/cad-viewer/scripts/viewer/dist/**" \
      2>/dev/null || true
  )"

  if [ -n "$tracked_dist" ]; then
    echo "skills/cad-viewer/scripts/viewer/dist must not be tracked on develop." >&2
    echo "Run scripts/dev/setup-symlinks.sh to restore the cad-viewer runtime symlink." >&2
    echo "$tracked_dist" | sed 's/^/- /' >&2
    return 1
  fi
}

cd "$REPO_ROOT"
setup_link "$MODE" "viewer/packages/cadjs" "../../packages/cadjs"
setup_link "$MODE" "viewer/packages/cadpy" "../../packages/cadpy"
setup_link "$MODE" "viewer/packages/implicitjs" "../../packages/implicitjs"
setup_link "$MODE" "skills/cad-viewer/scripts/viewer" "../../../viewer"
if [ "$MODE" = "check" ]; then
  check_no_tracked_runtime_dist
fi
