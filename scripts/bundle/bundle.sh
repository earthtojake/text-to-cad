#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="write"
RUNTIME_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle.sh [--check] [--clean]

The one bundle entry point: stamps derived version metadata from VERSION, then builds
cadgen's packaged runtime (packages/cadgen/src/cadgen/_runtime) with
scripts/bundle/cadgen-runtime.sh.

Options:
  --check     Build into tmp/ and fail if the committed outputs are stale.
  --clean     Remove temporary build/check directories first.
  -h, --help  Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
      RUNTIME_ARGS+=("--check")
      ;;
    --clean)
      RUNTIME_ARGS+=("--clean")
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
  echo "Checking the packaged runtime..."
else
  echo "Syncing derived version metadata..."
  node "$REPO_ROOT/scripts/release/sync-version.mjs"
  echo "Building the packaged runtime..."
fi

"$SCRIPT_DIR/cadgen-runtime.sh" "${RUNTIME_ARGS[@]+"${RUNTIME_ARGS[@]}"}"

if [ "$MODE" = "check" ]; then
  echo "All bundle outputs are up to date."
else
  echo "Bundled all production outputs."
fi
