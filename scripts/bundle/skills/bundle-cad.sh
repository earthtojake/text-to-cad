#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MODE="write"
CLEAN=0
INSTALL_DEPS=1

ESBUILD_VERSION="${CAD_SNAPSHOT_ESBUILD_VERSION:-0.27.7}"
THREE_VERSION="${CAD_SNAPSHOT_THREE_VERSION:-0.160.0}"
GIFENC_VERSION="${CAD_SNAPSHOT_GIFENC_VERSION:-1.0.3}"

BUILD_DEPS_DIR="${CAD_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/cad-snapshot-build}"
CHECK_DIR="${CAD_SNAPSHOT_CHECK_DIR:-$REPO_ROOT/tmp/cad-snapshot-runtime-check}"
RUNTIME_DIR="$REPO_ROOT/skills/cad/scripts/cadpy_snapshot/runtime"
ENTRYPOINT="$REPO_ROOT/packages/cadjs/src/common/headlessRenderEntry.js"
CADPY_PACKAGE_DIR="$REPO_ROOT/packages/cadpy"
CADPY_RUNTIME_DIR="$REPO_ROOT/skills/cad/scripts/packages/cadpy"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh cad [--check] [--clean] [--no-install]

Bundles the self-contained browser runtime used by skills/cad/scripts/cadpy_snapshot
and the bundled Python package runtime used by skills/cad/scripts.

Options:
  --check       Bundle into tmp/ and fail if snapshot/runtime is stale.
  --clean       Remove the temporary dependency/build directories first.
  --no-install  Require existing build dependencies in tmp/cad-snapshot-build.
  -h, --help    Show this help.
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
    --no-install)
      INSTALL_DEPS=0
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

if [ ! -f "$ENTRYPOINT" ]; then
  echo "Missing snapshot render entrypoint: $ENTRYPOINT" >&2
  echo "The CAD snapshot runtime is built from the same shared render entrypoint used by CAD Viewer." >&2
  exit 1
fi

if [ ! -f "$CADPY_PACKAGE_DIR/pyproject.toml" ] || [ ! -d "$CADPY_PACKAGE_DIR/src/cadpy" ]; then
  echo "Missing cadpy package source: $CADPY_PACKAGE_DIR" >&2
  echo "The CAD skill Python runtime is bundled from packages/cadpy." >&2
  exit 1
fi

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$BUILD_DEPS_DIR" "$CHECK_DIR"
fi

need_install() {
  [ -x "$BUILD_DEPS_DIR/node_modules/.bin/esbuild" ] || return 0
  node <<EOF || return 0
const deps = {
  esbuild: "$ESBUILD_VERSION",
  three: "$THREE_VERSION",
  gifenc: "$GIFENC_VERSION",
};
for (const [name, expected] of Object.entries(deps)) {
  const actual = require("$BUILD_DEPS_DIR/node_modules/" + name + "/package.json").version;
  if (actual !== expected) {
    process.exit(1);
  }
}
EOF
  return 1
}

ensure_deps() {
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync is required to build the CAD skill Python runtime." >&2
    exit 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build the CAD snapshot runtime." >&2
    exit 1
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo "node is required to build the CAD snapshot runtime." >&2
    exit 1
  fi
  if need_install; then
    if [ "$INSTALL_DEPS" -eq 0 ]; then
      echo "Missing or stale build dependencies in $BUILD_DEPS_DIR." >&2
      echo "Run without --no-install to install them." >&2
      exit 1
    fi
    mkdir -p "$BUILD_DEPS_DIR"
    npm install --prefix "$BUILD_DEPS_DIR" --no-audit --no-fund \
      --fetch-retries=1 --fetch-timeout=10000 \
      "esbuild@$ESBUILD_VERSION" \
      "three@$THREE_VERSION" \
      "gifenc@$GIFENC_VERSION"
  fi
}

write_render_html() {
  local target_dir="$1"
  cat > "$target_dir/render.html" <<'EOF'
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>CAD snapshot render</title>
    <style>
      html,
      body {
        margin: 0;
        min-width: 100%;
        min-height: 100%;
        overflow: hidden;
        background: transparent;
      }
    </style>
  </head>
  <body>
    <script type="module" src="/snapshot-render.js"></script>
  </body>
</html>
EOF
}

build_runtime() {
  local target_dir="$1"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  write_render_html "$target_dir"
  "$BUILD_DEPS_DIR/node_modules/.bin/esbuild" "$ENTRYPOINT" \
    --bundle \
    --format=esm \
    --platform=browser \
    --target=es2022 \
    --main-fields=module,main \
    --minify \
    --legal-comments=none \
    --alias:three="$BUILD_DEPS_DIR/node_modules/three" \
    --alias:gifenc="$BUILD_DEPS_DIR/node_modules/gifenc/dist/gifenc.esm.js" \
    --outfile="$target_dir/snapshot-render.js"
}

sync_cadpy_runtime() {
  local target_dir="$1"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  rsync -a --delete \
    --delete-excluded \
    --exclude __pycache__ \
    --exclude .pytest_cache \
    --exclude '*.pyc' \
    --exclude '*.md' \
    --exclude build \
    --exclude dist \
    --exclude '*.egg-info' \
    --exclude tests \
    --exclude __tests__ \
    --exclude 'test_*.py' \
    --exclude '*_test.py' \
    "$CADPY_PACKAGE_DIR/" "$target_dir/"
}

check_runtime() {
  local stale=0
  for file in render.html snapshot-render.js; do
    if [ ! -f "$RUNTIME_DIR/$file" ]; then
      echo "Missing generated runtime file: skills/cad/scripts/cadpy_snapshot/runtime/$file" >&2
      stale=1
      continue
    fi
    if ! cmp -s "$CHECK_DIR/$file" "$RUNTIME_DIR/$file"; then
      echo "Stale generated runtime file: skills/cad/scripts/cadpy_snapshot/runtime/$file" >&2
      stale=1
    fi
  done
  if [ "$stale" -ne 0 ]; then
    echo "" >&2
    echo "Run scripts/bundle/bundle-skill.sh cad and commit the updated runtime files." >&2
    exit 1
  fi
  echo "CAD snapshot runtime is up to date."
}

check_cadpy_runtime() {
  local check_dir="$CHECK_DIR/packages/cadpy"
  if [ ! -d "$CADPY_RUNTIME_DIR" ]; then
    echo "Missing generated cadpy runtime: skills/cad/scripts/packages/cadpy" >&2
    echo "" >&2
    echo "Run scripts/bundle/bundle-skill.sh cad and commit the updated runtime files." >&2
    exit 1
  fi
  if ! diff -qr \
    -x __pycache__ \
    -x .pytest_cache \
    -x '*.pyc' \
    -x '*.egg-info' \
    -x '*.md' \
    -x tests \
    -x __tests__ \
    -x 'test_*.py' \
    -x '*_test.py' \
    "$check_dir" "$CADPY_RUNTIME_DIR" >/tmp/cad-skill-cadpy-runtime-diff.txt; then
    cat /tmp/cad-skill-cadpy-runtime-diff.txt >&2
    echo "" >&2
    echo "CAD skill cadpy runtime is stale." >&2
    echo "Run scripts/bundle/bundle-skill.sh cad and commit skills/cad/scripts/packages/cadpy." >&2
    exit 1
  fi
  echo "CAD skill cadpy runtime is up to date."
}

ensure_deps

if [ "$MODE" = "check" ]; then
  build_runtime "$CHECK_DIR"
  sync_cadpy_runtime "$CHECK_DIR/packages/cadpy"
  check_runtime
  check_cadpy_runtime
else
  build_runtime "$RUNTIME_DIR"
  sync_cadpy_runtime "$CADPY_RUNTIME_DIR"
  echo "Bundled skills/cad/scripts/cadpy_snapshot/runtime"
  echo "Bundled skills/cad/scripts/packages/cadpy"
fi
