#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/vendor.sh
source "$SCRIPT_DIR/../lib/vendor.sh"

MODE="write"
BUILD=1
CLEAN=0
PRINT_OUTPUTS=0

CADJS_PACKAGE_DIR="$REPO_ROOT/packages/cadjs"
CADPY_PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
IMPLICITJS_PACKAGE_DIR="$REPO_ROOT/packages/implicitjs"
VIEWER_DIR="$REPO_ROOT/viewer"
VIEWER_CADJS_DIR="$VIEWER_DIR/packages/cadjs"
VIEWER_CADPY_DIR="$VIEWER_DIR/packages/cadgen"
VIEWER_IMPLICITJS_DIR="$VIEWER_DIR/packages/implicitjs"
RUNTIME_DIR="$REPO_ROOT/skills/cad-viewer/scripts/viewer"
CHECK_DIR="${CAD_VIEWER_RUNTIME_CHECK_DIR:-${RENDER_VIEWER_RUNTIME_CHECK_DIR:-$REPO_ROOT/tmp/cad-viewer-runtime-check}}"
VIEWER_PACKAGE_MANAGER="${CAD_VIEWER_PACKAGE_MANAGER:-}"
ESBUILD_BIN="${CAD_VIEWER_ESBUILD_BIN:-}"
RELEASE_VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"

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
  --print-outputs
              Print the repo-relative generated output paths, then exit.
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
    --print-outputs)
      PRINT_OUTPUTS=1
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

if [ "$PRINT_OUTPUTS" -eq 1 ]; then
  printf '%s\n' \
    "${VIEWER_CADJS_DIR#"$REPO_ROOT"/}" \
    "${VIEWER_CADPY_DIR#"$REPO_ROOT"/}" \
    "${VIEWER_IMPLICITJS_DIR#"$REPO_ROOT"/}" \
    "${RUNTIME_DIR#"$REPO_ROOT"/}"
  exit 0
fi

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

# The COMMITTED lockfile decides, not what happens to be installed on this machine. The
# repository commits viewer/package-lock.json, so preferring pnpm merely because it is on
# PATH made the release build depend on the builder's laptop: pnpm and npm lay out
# node_modules differently (which is why resolve_esbuild_bin has to search .pnpm at all),
# so the same source revision could be bundled against a different tree. The committed npm
# lockfile is checked first on purpose: a stray local `pnpm install` leaves an untracked
# pnpm-lock.yaml behind, and that must not be able to flip a release build either. An explicit
# CAD_VIEWER_PACKAGE_MANAGER still wins -- someone deliberately switching should not have to
# delete a lockfile to do it.
resolve_viewer_package_manager() {
  if [ -n "$VIEWER_PACKAGE_MANAGER" ]; then
    echo "$VIEWER_PACKAGE_MANAGER"
    return
  fi
  if [ -f "$VIEWER_DIR/package-lock.json" ]; then
    echo "npm"
    return
  fi
  if [ -f "$VIEWER_DIR/pnpm-lock.yaml" ]; then
    echo "pnpm"
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
    --exclude /common \
    --exclude /lib \
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

sync_cadgen_package() {
  # Canonical Python vendoring lives in scripts/bundle/lib/vendor.sh.
  vendor_python_package "$1" "$2"
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

check_cadgen_package() {
  check_python_runtime "$CADPY_PACKAGE_DIR" "$VIEWER_CADPY_DIR" \
    "${TMPDIR:-/tmp}/viewer-cadgen-package-check" "${VIEWER_CADPY_DIR#$REPO_ROOT/}" \
    "Run scripts/bundle/bundle-skill.sh cad-viewer and commit viewer/packages/cadgen."
}

build_viewer_packages() {
  if [ "$CLEAN" -eq 1 ]; then
    rm -rf "$VIEWER_CADJS_DIR"
    rm -rf "$VIEWER_CADPY_DIR"
    rm -rf "$VIEWER_IMPLICITJS_DIR"
  fi
  sync_cadjs_package
  sync_cadgen_package "$CADPY_PACKAGE_DIR" "$VIEWER_CADPY_DIR"
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
  if [ -L "$cadjs_node_module" ]; then
    return
  fi
  local subpath
  for subpath in common lib; do
    if [ -d "$VIEWER_CADJS_DIR/src/$subpath" ] && [ ! -e "$cadjs_node_module/$subpath/cadScene.js" ] && [ ! -e "$cadjs_node_module/$subpath/pathUtils.mjs" ]; then
      rm -rf "$cadjs_node_module/$subpath"
      ln -s "$VIEWER_CADJS_DIR/src/$subpath" "$cadjs_node_module/$subpath"
    fi
  done
}

check_viewer_packages() {
  check_cadjs_package
  check_cadgen_package
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
    "start": "node scripts/start-viewer.mjs",
    "serve": "python3 -m server_py.server",
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
--editable ./packages/cadgen
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
  mkdir -p "$target_dir"

  sync_dir "$VIEWER_DIR/dist" "$target_dir/dist"

  if [ -d "$VIEWER_DIR/moveit2_server" ]; then
    sync_dir "$VIEWER_DIR/moveit2_server" "$target_dir/moveit2_server"
  fi

  sync_dir "$VIEWER_DIR/packages" "$target_dir/packages"

  # Python backend (server_py): the runtime serves the built dist + /__cad. STEP
  # build/export run through the persistent warm-OCCT worker (server_py/worker.py +
  # worker_client.py), falling back to a cold `python -m cadgen.<module>` subprocess;
  # both use the editable-installed cadgen (requirements.txt). sync_dir excludes
  # tests/__pycache__/golden so only runtime modules ship (worker.py included,
  # tests/test_worker.py not).
  sync_dir "$VIEWER_DIR/server_py" "$target_dir/server_py"

  # The `npm start` launcher, which the skill documents as the way to start the Viewer. Named
  # files rather than the whole scripts/ directory: that directory also carries e2e harnesses and
  # a theme baseline, none of which belong in a runtime.
  mkdir -p "$target_dir/scripts"
  for launcher_file in start-viewer.mjs cad-python.mjs directoryRoot.mjs; do
    cp "$VIEWER_DIR/scripts/$launcher_file" "$target_dir/scripts/$launcher_file"
  done

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
require_path "$CADPY_PACKAGE_DIR/pyproject.toml" "cadgen package"
require_path "$CADPY_PACKAGE_DIR/src/cadgen" "cadgen source"
require_path "$IMPLICITJS_PACKAGE_DIR/package.json" "implicitjs package"
require_path "$IMPLICITJS_PACKAGE_DIR/src" "implicitjs source"
require_path "$VIEWER_DIR/package.json" "viewer package"
require_path "$VIEWER_DIR/server_py/server.py" "viewer Python backend"

if [ "$MODE" = "check" ]; then
  check_viewer_packages
else
  build_viewer_packages
fi
require_path "$VIEWER_CADPY_DIR/pyproject.toml" "viewer cadgen package"
require_path "$VIEWER_CADPY_DIR/src/cadgen" "viewer cadgen source"
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
