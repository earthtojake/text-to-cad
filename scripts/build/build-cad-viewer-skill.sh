#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="write"
BUILD=1
CLEAN=0

VIEWER_DIR="$REPO_ROOT/viewer"
BUILD_VIEWER_SCRIPT="$SCRIPT_DIR/build-viewer.sh"
VIEWER_CADPY_DIR="$VIEWER_DIR/packages/cadpy"
RUNTIME_DIR="$REPO_ROOT/skills/cad-viewer/scripts/viewer"
CHECK_DIR="${CAD_VIEWER_RUNTIME_CHECK_DIR:-${RENDER_VIEWER_RUNTIME_CHECK_DIR:-$REPO_ROOT/tmp/cad-viewer-runtime-check}}"
ESBUILD_BIN="$VIEWER_DIR/node_modules/.bin/esbuild"

usage() {
  cat <<'EOF'
Usage:
  scripts/build/build-cad-viewer-skill.sh [--check] [--clean] [--no-build]

Builds the self-contained production CAD Viewer runtime used by skills/cad-viewer.

Options:
  --check     Build into tmp/ and fail if skills/cad-viewer/scripts/viewer is stale.
  --clean     Remove the temporary check directory first.
  --no-build  Reuse the current viewer/dist instead of running npm run build.
  -h, --help  Show this help.
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
    --no-build)
      BUILD=0
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

require_path() {
  local path_to_check="$1"
  local label="$2"
  if [ ! -e "$path_to_check" ]; then
    echo "Missing $label: $path_to_check" >&2
    exit 1
  fi
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required to build the CAD Viewer runtime." >&2
    exit 1
  fi
}

write_runtime_package_json() {
  local target_dir="$1"
  cat > "$target_dir/package.json" <<'EOF'
{
  "name": "cad-viewer-runtime",
  "private": true,
  "type": "module",
  "version": "0.1.6",
  "scripts": {
    "serve": "node backend/server.mjs",
    "serve:ensure": "node scripts/ensure-serve.mjs",
    "start": "node backend/server.mjs",
    "moveit2:setup": "moveit2_server/setup.sh",
    "moveit2:check": "moveit2_server/check-moveit2-server.sh",
    "moveit2:serve": "moveit2_server/run-moveit2-server.sh"
  }
}
EOF
}

write_runtime_gitignore() {
  local target_dir="$1"
  cat > "$target_dir/.gitignore" <<'EOF'
node_modules
.env
.env.*
!.env.example
!.env.*.example
__pycache__
*.py[cod]
.pytest_cache
tmp

!dist
!dist/**
EOF
}

write_runtime_requirements() {
  local target_dir="$1"
  cat > "$target_dir/requirements.txt" <<'EOF'
--editable ./packages/cadpy
EOF
}

sync_dir() {
  local source_dir="$1"
  local target_dir="$2"
  mkdir -p "$target_dir"
  rsync -a --delete \
    --prune-empty-dirs \
    --delete-excluded \
    --exclude node_modules \
    --exclude build \
    --exclude dist \
    --exclude .vite \
    --exclude .pytest_cache \
    --exclude __pycache__ \
    --exclude '*.pyc' \
    --exclude '*.egg-info' \
    --exclude '*.md' \
    --exclude '*.test.js' \
    --exclude '*.test.mjs' \
    --exclude tests \
    "$source_dir/" "$target_dir/"
}

build_runtime() {
  local target_dir="$1"
  rm -rf "$target_dir"
  mkdir -p "$target_dir/backend" "$target_dir/scripts"

  sync_dir "$VIEWER_DIR/dist" "$target_dir/dist"

  if [ -d "$VIEWER_DIR/moveit2_server" ]; then
    sync_dir "$VIEWER_DIR/moveit2_server" "$target_dir/moveit2_server"
  fi

  sync_dir "$VIEWER_DIR/packages" "$target_dir/packages"

  (
    cd "$REPO_ROOT"
    "$ESBUILD_BIN" "$VIEWER_DIR/src/server/server.mjs" \
      --bundle \
      --format=esm \
      --platform=node \
      --target=node22 \
      --main-fields=module,main \
      --legal-comments=none \
      --outfile="$target_dir/backend/server.mjs"

    "$ESBUILD_BIN" "$VIEWER_DIR/scripts/ensure-serve.mjs" \
      --bundle \
      --format=esm \
      --platform=node \
      --target=node22 \
      --main-fields=module,main \
      --legal-comments=none \
      --outfile="$target_dir/scripts/ensure-serve.mjs"
  )

  write_runtime_package_json "$target_dir"
  write_runtime_gitignore "$target_dir"
  write_runtime_requirements "$target_dir"
}

check_runtime() {
  if ! diff -qr \
    -x __pycache__ \
    -x .pytest_cache \
    -x '*.pyc' \
    -x '*.egg-info' \
    "$CHECK_DIR" "$RUNTIME_DIR" >/tmp/cad-viewer-runtime-diff.txt; then
    cat /tmp/cad-viewer-runtime-diff.txt >&2
    echo "" >&2
    echo "CAD Viewer runtime is stale." >&2
    echo "Run scripts/build/build-cad-viewer-skill.sh and commit skills/cad-viewer/scripts/viewer." >&2
    exit 1
  fi
  echo "CAD Viewer runtime is up to date."
}

require_command npm
require_command rsync
require_path "$BUILD_VIEWER_SCRIPT" "viewer build script"
require_path "$VIEWER_DIR/package.json" "viewer package"
require_path "$ESBUILD_BIN" "viewer esbuild binary; run npm install --prefix viewer"

BUILD_VIEWER_ARGS=()
if [ "$MODE" = "check" ]; then
  BUILD_VIEWER_ARGS+=("--check")
fi
if [ "$CLEAN" -eq 1 ]; then
  BUILD_VIEWER_ARGS+=("--clean")
fi
if [ "${#BUILD_VIEWER_ARGS[@]}" -gt 0 ]; then
  "$BUILD_VIEWER_SCRIPT" "${BUILD_VIEWER_ARGS[@]}"
else
  "$BUILD_VIEWER_SCRIPT"
fi
require_path "$VIEWER_CADPY_DIR/pyproject.toml" "viewer cadpy package"
require_path "$VIEWER_CADPY_DIR/src/cadpy" "viewer cadpy source"

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR"
fi

if [ "$BUILD" -eq 1 ]; then
  npm --prefix "$VIEWER_DIR" run build
fi

require_path "$VIEWER_DIR/dist/index.html" "viewer production build"

if [ "$MODE" = "check" ]; then
  build_runtime "$CHECK_DIR"
  check_runtime
else
  build_runtime "$RUNTIME_DIR"
  echo "Built skills/cad-viewer/scripts/viewer"
fi
