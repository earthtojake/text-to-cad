#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MODE="write"
BUILD=1
CLEAN=0

CADJS_PACKAGE_DIR="$REPO_ROOT/packages/cadjs"
CADPY_PACKAGE_DIR="$REPO_ROOT/packages/cadpy"
IMPLICITJS_PACKAGE_DIR="$REPO_ROOT/packages/implicitjs"
VIEWER_DIR="$REPO_ROOT/viewer"
VIEWER_CADJS_DIR="$VIEWER_DIR/packages/cadjs"
VIEWER_CADPY_DIR="$VIEWER_DIR/packages/cadpy"
VIEWER_IMPLICITJS_DIR="$VIEWER_DIR/packages/implicitjs"
RUNTIME_DIR="$REPO_ROOT/skills/cad-viewer/scripts/viewer"
CHECK_DIR="${CAD_VIEWER_RUNTIME_CHECK_DIR:-${RENDER_VIEWER_RUNTIME_CHECK_DIR:-$REPO_ROOT/tmp/cad-viewer-runtime-check}}"
VIEWER_PACKAGE_MANAGER="${CAD_VIEWER_PACKAGE_MANAGER:-}"
ESBUILD_BIN="${CAD_VIEWER_ESBUILD_BIN:-}"
RELEASE_VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/plugins/cad/VERSION")"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh cad-viewer [--check] [--clean] [--no-build]

Bundles the viewer-local package copies and the self-contained production CAD
Viewer runtime used by skills/cad-viewer. Client sourcemaps are included so
installed skill runtimes can be debugged from browser DevTools.

Options:
  --check     Bundle into tmp/ and fail if viewer package copies or
              skills/cad-viewer/scripts/viewer are stale.
  --clean     Remove generated package copies and temporary check directories first.
  --no-build  Reuse the current viewer/dist instead of rebuilding the viewer.
              The existing dist must already include client sourcemaps.
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

resolve_viewer_package_manager() {
  if [ -n "$VIEWER_PACKAGE_MANAGER" ]; then
    echo "$VIEWER_PACKAGE_MANAGER"
    return
  fi
  if command -v pnpm >/dev/null 2>&1; then
    echo "pnpm"
    return
  fi
  echo "npm"
}

run_viewer_build() {
  local package_manager
  package_manager="$(resolve_viewer_package_manager)"
  require_command "$package_manager"
  case "$package_manager" in
    pnpm)
      CI=true pnpm --dir "$VIEWER_DIR" run build --sourcemap true
      ;;
    npm)
      npm --prefix "$VIEWER_DIR" run build -- --sourcemap true
      ;;
    *)
      echo "Unsupported CAD Viewer package manager: $package_manager" >&2
      echo "Set CAD_VIEWER_PACKAGE_MANAGER to pnpm or npm." >&2
      exit 1
      ;;
  esac
}

resolve_esbuild_bin() {
  if [ -n "$ESBUILD_BIN" ]; then
    echo "$ESBUILD_BIN"
    return
  fi
  if [ -x "$VIEWER_DIR/node_modules/.bin/esbuild" ]; then
    echo "$VIEWER_DIR/node_modules/.bin/esbuild"
    return
  fi
  local pnpm_esbuild_bin
  pnpm_esbuild_bin="$(find "$VIEWER_DIR/node_modules/.pnpm" -path '*/node_modules/esbuild/bin/esbuild' -type f -perm -111 -print -quit 2>/dev/null || true)"
  if [ -n "$pnpm_esbuild_bin" ]; then
    echo "$pnpm_esbuild_bin"
    return
  fi
  echo "$VIEWER_DIR/node_modules/.bin/esbuild"
}

require_client_sourcemaps() {
  local dist_dir="$1"
  local map_count
  if [ ! -d "$dist_dir/assets" ]; then
    echo "Missing Viewer dist assets directory: $dist_dir/assets" >&2
    exit 1
  fi
  map_count="$(find "$dist_dir/assets" -type f -name '*.map' | wc -l | tr -d '[:space:]')"
  if [ "$map_count" -eq 0 ]; then
    echo "Missing Viewer client sourcemaps in $dist_dir/assets." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer without --no-build to regenerate viewer/dist with sourcemaps." >&2
    exit 1
  fi
}

sync_cadjs_package() {
  local target_dir="${1:-$VIEWER_CADJS_DIR}"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  rsync -a --delete \
    --prune-empty-dirs \
    --delete-excluded \
    --exclude node_modules \
    --exclude dist \
    --exclude coverage \
    --exclude tmp \
    --exclude .vite \
    --exclude .DS_Store \
    --exclude tests \
    --exclude __tests__ \
    --exclude '*.test.js' \
    --exclude '*.test.mjs' \
    --exclude '*.test.ts' \
    --exclude '*.test.tsx' \
    --exclude '*.spec.js' \
    --exclude '*.spec.mjs' \
    --exclude '*.spec.ts' \
    --exclude '*.spec.tsx' \
    "$CADJS_PACKAGE_DIR/" "$target_dir/"
}

sync_implicitjs_package() {
  local target_dir="${1:-$VIEWER_IMPLICITJS_DIR}"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  rsync -a --delete \
    --prune-empty-dirs \
    --delete-excluded \
    --exclude node_modules \
    --exclude dist \
    --exclude coverage \
    --exclude tmp \
    --exclude .vite \
    --exclude .DS_Store \
    "$IMPLICITJS_PACKAGE_DIR/" "$target_dir/"
}

sync_cadpy_package() {
  local source_dir="$1"
  local target_dir="$2"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  rsync -a --delete \
    --prune-empty-dirs \
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
    "$source_dir/" "$target_dir/"
}

check_cadjs_package() {
  local label="${VIEWER_CADJS_DIR#$REPO_ROOT/}"
  local diff_path="${TMPDIR:-/tmp}/viewer-cadjs-package-diff.txt"
  local expected_dir="${TMPDIR:-/tmp}/viewer-cadjs-package-check"
  if [ ! -d "$VIEWER_CADJS_DIR" ]; then
    echo "Missing generated viewer cadjs package: $label" >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit the generated copy." >&2
    exit 1
  fi
  rm -rf "$expected_dir"
  sync_cadjs_package "$expected_dir"
  if ! diff -qr \
    -x node_modules \
    -x dist \
    -x coverage \
    -x tmp \
    -x .vite \
    -x .DS_Store \
    -x tests \
    -x __tests__ \
    -x '*.test.js' \
    -x '*.test.mjs' \
    -x '*.test.ts' \
    -x '*.test.tsx' \
    -x '*.spec.js' \
    -x '*.spec.mjs' \
    -x '*.spec.ts' \
    -x '*.spec.tsx' \
    "$expected_dir" "$VIEWER_CADJS_DIR" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "Viewer cadjs package is stale." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit viewer/packages/cadjs." >&2
    exit 1
  fi
  echo "$label is up to date."
}

check_implicitjs_package() {
  local label="${VIEWER_IMPLICITJS_DIR#$REPO_ROOT/}"
  local diff_path="${TMPDIR:-/tmp}/viewer-implicitjs-package-diff.txt"
  local expected_dir="${TMPDIR:-/tmp}/viewer-implicitjs-package-check"
  if [ ! -d "$VIEWER_IMPLICITJS_DIR" ]; then
    echo "Missing generated viewer implicitjs package: $label" >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit the generated copy." >&2
    exit 1
  fi
  rm -rf "$expected_dir"
  sync_implicitjs_package "$expected_dir"
  if ! diff -qr \
    -x node_modules \
    -x dist \
    -x coverage \
    -x tmp \
    -x .vite \
    -x .DS_Store \
    "$expected_dir" "$VIEWER_IMPLICITJS_DIR" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "Viewer implicitjs package is stale." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit viewer/packages/implicitjs." >&2
    exit 1
  fi
  echo "$label is up to date."
}

check_cadpy_package() {
  local label="${VIEWER_CADPY_DIR#$REPO_ROOT/}"
  local diff_path="${TMPDIR:-/tmp}/viewer-cadpy-package-diff.txt"
  local expected_dir="${TMPDIR:-/tmp}/viewer-cadpy-package-check"
  if [ ! -d "$VIEWER_CADPY_DIR" ]; then
    echo "Missing generated viewer cadpy package: $label" >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit the generated copy." >&2
    exit 1
  fi
  rm -rf "$expected_dir"
  sync_cadpy_package "$CADPY_PACKAGE_DIR" "$expected_dir"
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
    "$expected_dir" "$VIEWER_CADPY_DIR" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "Viewer cadpy package is stale." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit viewer/packages/cadpy." >&2
    exit 1
  fi
  echo "$label is up to date."
}

build_viewer_packages() {
  if [ "$CLEAN" -eq 1 ]; then
    rm -rf "$VIEWER_CADJS_DIR"
    rm -rf "$VIEWER_CADPY_DIR"
    rm -rf "$VIEWER_IMPLICITJS_DIR"
  fi
  sync_cadjs_package
  sync_cadpy_package "$CADPY_PACKAGE_DIR" "$VIEWER_CADPY_DIR"
  sync_implicitjs_package
  echo "Bundled ${VIEWER_CADJS_DIR#$REPO_ROOT/}"
  echo "Bundled ${VIEWER_CADPY_DIR#$REPO_ROOT/}"
  echo "Bundled ${VIEWER_IMPLICITJS_DIR#$REPO_ROOT/}"
}

ensure_viewer_cadjs_node_module_subpaths() {
  local cadjs_node_module="$VIEWER_DIR/node_modules/cadjs"
  if [ ! -d "$cadjs_node_module" ]; then
    return
  fi
  local subpath
  for subpath in common lib; do
    if [ -d "$VIEWER_CADJS_DIR/src/$subpath" ] && [ ! -e "$cadjs_node_module/$subpath/stepSidecars.mjs" ] && [ ! -e "$cadjs_node_module/$subpath/pathUtils.mjs" ]; then
      rm -rf "$cadjs_node_module/$subpath"
      ln -s "$VIEWER_CADJS_DIR/src/$subpath" "$cadjs_node_module/$subpath"
    fi
  done
}

check_viewer_packages() {
  check_cadjs_package
  check_cadpy_package
  check_implicitjs_package
}

write_runtime_package_json() {
  local target_dir="$1"
  cat > "$target_dir/package.json" <<EOF
{
  "name": "cad-viewer-runtime",
  "private": true,
  "type": "module",
  "version": "$RELEASE_VERSION",
  "scripts": {
    "serve": "node backend/server.mjs",
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
    --exclude '*.test.ts' \
    --exclude '*.test.tsx' \
    --exclude '*.spec.js' \
    --exclude '*.spec.mjs' \
    --exclude '*.spec.ts' \
    --exclude '*.spec.tsx' \
    --exclude tests \
    --exclude __tests__ \
    --exclude 'test_*.py' \
    --exclude '*_test.py' \
    "$source_dir/" "$target_dir/"
}

build_runtime() {
  local target_dir="$1"
  rm -rf "$target_dir"
  mkdir -p "$target_dir/backend"

  sync_dir "$VIEWER_DIR/dist" "$target_dir/dist"

  if [ -d "$VIEWER_DIR/moveit2_server" ]; then
    sync_dir "$VIEWER_DIR/moveit2_server" "$target_dir/moveit2_server"
  fi

  sync_dir "$VIEWER_DIR/packages" "$target_dir/packages"

  (
    cd "$REPO_ROOT"
    "$(resolve_esbuild_bin)" "$VIEWER_DIR/src/server/server.mjs" \
      --bundle \
      --format=esm \
      --platform=node \
      --target=node22 \
      --main-fields=module,main \
      --legal-comments=none \
      --outfile="$target_dir/backend/server.mjs"

  )

  write_runtime_package_json "$target_dir"
  write_runtime_gitignore "$target_dir"
  write_runtime_requirements "$target_dir"
}

check_runtime() {
  if [ -L "$RUNTIME_DIR" ]; then
    echo "CAD Viewer runtime is in development symlink layout; production runtime diff is checked on build-test/main."
    return
  fi
  if ! diff -qr \
    -x __pycache__ \
    -x .pytest_cache \
    -x '*.pyc' \
    -x '*.egg-info' \
    "$CHECK_DIR" "$RUNTIME_DIR" >/tmp/cad-viewer-runtime-diff.txt; then
    cat /tmp/cad-viewer-runtime-diff.txt >&2
    echo "" >&2
    echo "CAD Viewer runtime is stale." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad-viewer and commit skills/cad-viewer/scripts/viewer." >&2
    exit 1
  fi
  echo "CAD Viewer runtime is up to date."
}

require_command rsync
require_path "$CADJS_PACKAGE_DIR/package.json" "cadjs package"
require_path "$CADJS_PACKAGE_DIR/src" "cadjs source"
require_path "$CADPY_PACKAGE_DIR/pyproject.toml" "cadpy package"
require_path "$CADPY_PACKAGE_DIR/src/cadpy" "cadpy source"
require_path "$IMPLICITJS_PACKAGE_DIR/package.json" "implicitjs package"
require_path "$IMPLICITJS_PACKAGE_DIR/src" "implicitjs source"
require_path "$VIEWER_DIR/package.json" "viewer package"
require_path "$(resolve_esbuild_bin)" "viewer esbuild binary; install viewer dependencies"

if [ "$MODE" = "check" ]; then
  check_viewer_packages
else
  build_viewer_packages
fi
require_path "$VIEWER_CADPY_DIR/pyproject.toml" "viewer cadpy package"
require_path "$VIEWER_CADPY_DIR/src/cadpy" "viewer cadpy source"
require_path "$VIEWER_IMPLICITJS_DIR/package.json" "viewer implicitjs package"
require_path "$VIEWER_IMPLICITJS_DIR/src" "viewer implicitjs source"

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR"
fi

if [ "$BUILD" -eq 1 ]; then
  ensure_viewer_cadjs_node_module_subpaths
  run_viewer_build
fi

require_path "$VIEWER_DIR/dist/index.html" "viewer production bundle"
require_client_sourcemaps "$VIEWER_DIR/dist"

if [ "$MODE" = "check" ]; then
  build_runtime "$CHECK_DIR"
  check_runtime
else
  build_runtime "$RUNTIME_DIR"
  echo "Bundled skills/cad-viewer/scripts/viewer"
fi
