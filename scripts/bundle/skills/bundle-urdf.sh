#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MODE="write"
CLEAN=0
PACKAGE_DIR="$REPO_ROOT/packages/cadpy_metadata"
RUNTIME_DIR="$REPO_ROOT/skills/urdf/scripts/packages/cadpy_metadata"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh urdf [--check] [--clean]

Vendors packages/cadpy_metadata into skills/urdf/scripts/packages/cadpy_metadata.

Options:
  --check  Fail if the generated URDF skill runtime copy is stale.
  --clean  Remove the generated runtime copy before writing it.
  -h, --help
           Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
      ;;
    --clean)
      CLEAN=1
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

if [ ! -f "$PACKAGE_DIR/pyproject.toml" ] || [ ! -d "$PACKAGE_DIR/src/cadpy_metadata" ]; then
  echo "Missing cadpy_metadata package source: $PACKAGE_DIR" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required to vendor cadpy_metadata into the URDF skill runtime." >&2
  exit 1
fi

sync_runtime() {
  rm -rf "$RUNTIME_DIR"
  mkdir -p "$RUNTIME_DIR"
  rsync -a --delete \
    --delete-excluded \
    --exclude __pycache__ \
    --exclude .pytest_cache \
    --exclude '*.pyc' \
    --exclude '*.egg-info' \
    --exclude '*.md' \
    --exclude build \
    --exclude dist \
    --exclude tests \
    --exclude __tests__ \
    --exclude 'test_*.py' \
    --exclude '*_test.py' \
    "$PACKAGE_DIR/" "$RUNTIME_DIR/"
}

check_runtime() {
  local label="${RUNTIME_DIR#$REPO_ROOT/}"
  local diff_path="${TMPDIR:-/tmp}/urdf-skill-cadpy-metadata-diff.txt"
  if [ ! -d "$RUNTIME_DIR" ]; then
    echo "Missing generated cadpy_metadata runtime: $label" >&2
    echo "Run scripts/bundle/bundle-skill.sh urdf and commit the generated copy." >&2
    exit 1
  fi
  if ! diff -qr \
    -x __pycache__ \
    -x .pytest_cache \
    -x '*.pyc' \
    -x '*.egg-info' \
    -x '*.md' \
    -x build \
    -x dist \
    -x tests \
    -x __tests__ \
    -x 'test_*.py' \
    -x '*_test.py' \
    "$PACKAGE_DIR" "$RUNTIME_DIR" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "Stale generated cadpy_metadata runtime: $label" >&2
    echo "Run scripts/bundle/bundle-skill.sh urdf and commit the generated copy." >&2
    exit 1
  fi
  echo "$label is up to date."
}

if [ "$MODE" = "check" ]; then
  check_runtime
else
  if [ "$CLEAN" -eq 1 ]; then
    rm -rf "$RUNTIME_DIR"
  fi
  sync_runtime
  echo "Bundled ${RUNTIME_DIR#$REPO_ROOT/}"
fi
