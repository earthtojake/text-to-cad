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
scripts/bundle/cadgen-runtime.sh. The runtime is gitignored and ships only inside the
wheel, so this is what produces it -- in a checkout, in CI, and before `python -m build`.

Options:
  --check     Build the runtime and assert every required output exists, and check
              that the derived version metadata matches VERSION rather than writing it.
  --clean     Remove the _runtime tree first, so the build starts from nothing.
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
  # The derived metadata IS committed, so --check still means "fresh" for it. The
  # runtime is not, so for that --check means "builds, and produced everything".
  echo "Checking derived version metadata..."
  node "$REPO_ROOT/scripts/release/sync-version.mjs" --check
  echo "Building and checking the packaged runtime..."
else
  echo "Syncing derived version metadata..."
  node "$REPO_ROOT/scripts/release/sync-version.mjs"
  echo "Building the packaged runtime..."
fi

# Shared ESM packages are the inputs consumed by hosts and runtime builders.
npm --prefix "$REPO_ROOT" run build:packages

"$SCRIPT_DIR/cadgen-runtime.sh" "${RUNTIME_ARGS[@]+"${RUNTIME_ARGS[@]}"}"

if [ "$MODE" = "check" ]; then
  echo "Derived metadata is up to date and the packaged runtime builds."
else
  echo "Bundled all production outputs."
fi
