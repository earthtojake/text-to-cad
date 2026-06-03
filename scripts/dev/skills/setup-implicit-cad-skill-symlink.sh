#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
UTILS_SCRIPT="$REPO_ROOT/scripts/dev/symlink-utils.sh"

MODE="write"

usage() {
  cat <<'EOF'
Usage:
  scripts/dev/setup-skill-symlink.sh implicit-cad [--check]

Sets up Implicit CAD skill development symlinks.

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

check_no_generated_runtimes() {
  local tracked_runtime
  tracked_runtime="$(
    git ls-files \
      "skills/implicit-cad/scripts/export/runtime" \
      "skills/implicit-cad/scripts/export/runtime/**" \
      "skills/implicit-cad/scripts/snapshot/runtime" \
      "skills/implicit-cad/scripts/snapshot/runtime/**" \
      2>/dev/null || true
  )"

  if [ -n "$tracked_runtime" ]; then
    echo "Implicit CAD generated runtimes must not be tracked on develop." >&2
    echo "Run scripts/dev/setup-symlinks.sh to restore the implicit-cad development layout." >&2
    echo "$tracked_runtime" | sed 's/^/- /' >&2
    return 1
  fi
}

cd "$REPO_ROOT"
setup_link "$MODE" "skills/implicit-cad/scripts/packages/implicitjs" "../../../../packages/implicitjs"
if [ "$MODE" = "check" ]; then
  check_no_generated_runtimes
fi
