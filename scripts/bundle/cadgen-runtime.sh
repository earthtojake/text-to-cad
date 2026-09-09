#!/usr/bin/env bash
set -euo pipefail

# Build cadgen's non-Python runtime INTO THE PACKAGE (packages/cadgen/src/cadgen/_runtime).
#
# cadgen executes three things it does not write in Python: Node builders (the DXF mesh
# and the mesh exports are baked by a JS child), a headless browser bundle (the snapshot
# CLI drives it in a page), and the CAD Viewer's built client (`cadgen viewer` serves
# it). cadgen.assets resolves all three inside the distribution, so there is one copy
# and one builder of that copy: this script. scripts/bundle/bundle.sh is the entry point
# that calls it (after stamping derived version metadata); call this directly only when
# debugging one stage.
#
# Stages (default: all of them):
#   --node      esbuilt builders          -> _runtime/node
#   --browser   snapshot browser bundle   -> _runtime/browser
#   --viewer    CAD Viewer client (vite)  -> _runtime/viewer
#
# NOTHING here is committed. The whole _runtime tree is gitignored and built on demand:
# the wheel is the only place these files ship, and a rebundle of the snapshot renderer
# alone was 1.3 MB of churn per commit. So there is no committed copy to diff against,
# and `--check` means "the runtime BUILDS and every required output is there" rather than
# "the committed copy is fresh": it builds into _runtime like a normal run and then
# asserts the files each stage owes. scripts/release/check-wheel-contents.sh is the gate
# that proves the wheel got them.
#
# `--check` skips the viewer stage because it is the expensive one (a vite build of
# apps/web, which needs that app's node_modules) and because a checkout serves
# apps/web/dist directly -- cadgen.assets prefers it, so nothing in a checkout reads
# _runtime/viewer. `--print-outputs` lists the two directories a bundle always produces.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUNDLE_REPO_ROOT="$REPO_ROOT"
# shellcheck source=lib/node_builders.sh
source "$SCRIPT_DIR/lib/node_builders.sh"
# shellcheck source=lib/snapshot_runtime.sh
source "$SCRIPT_DIR/lib/snapshot_runtime.sh"

RUNTIME_DIR="$REPO_ROOT/packages/cadgen/src/cadgen/_runtime"
NODE_DIR="$RUNTIME_DIR/node"
BROWSER_DIR="$RUNTIME_DIR/browser"
VIEWER_DIR="$RUNTIME_DIR/viewer"
VIEWER_APP_DIR="$REPO_ROOT/apps/web"
VIEWER_PACKAGE_MANAGER="${CAD_VIEWER_PACKAGE_MANAGER:-}"

SNAPSHOT_BUILD_DEPS_DIR="${CADGEN_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/cadgen-snapshot-build}"

# What each stage owes, checked after a --check build. A stage that emits nothing, or
# emits one file and silently drops another, is the failure this catches before a wheel
# carries the hole to a user.
NODE_OUTPUTS=(dxf-mesh.mjs mesh-export.mjs package.json THIRD_PARTY_LICENSES.txt)
BROWSER_OUTPUTS=(snapshot-render.js render.html THIRD_PARTY_LICENSES.txt)

BUILDER_ENTRIES=(
  "$REPO_ROOT/packages/core/bin/dxf-mesh.mjs"
  "$REPO_ROOT/packages/core/bin/mesh-export.mjs"
)

MODE="write"
CLEAN=0
PRINT_OUTPUTS=0
STAGE_NODE=0
STAGE_BROWSER=0
STAGE_VIEWER=0
ANY_STAGE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/cadgen-runtime.sh [--check] [--clean] [--print-outputs] [stages...]

Builds cadgen's packaged runtime assets into packages/cadgen/src/cadgen/_runtime.
None of it is committed; the wheel is where it ships.

Stages (default: all):
  --node      esbuilt Node builders     -> _runtime/node
  --browser   snapshot browser bundle   -> _runtime/browser
  --viewer    CAD Viewer client (vite)  -> _runtime/viewer

Options:
  --check          Build, then assert every required output exists. Skips the
                   viewer stage (a vite build nothing in a checkout reads).
  --clean          Remove the _runtime tree first, so the build starts from nothing.
  --print-outputs  Print the generated output paths (repo-relative), then exit.
  -h, --help       Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --clean) CLEAN=1 ;;
    --print-outputs) PRINT_OUTPUTS=1 ;;
    --node) STAGE_NODE=1; ANY_STAGE=1 ;;
    --browser) STAGE_BROWSER=1; ANY_STAGE=1 ;;
    --viewer) STAGE_VIEWER=1; ANY_STAGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$ANY_STAGE" -eq 0 ]; then
  STAGE_NODE=1; STAGE_BROWSER=1; STAGE_VIEWER=1
fi

if [ "$PRINT_OUTPUTS" -eq 1 ]; then
  printf '%s\n' \
    "${NODE_DIR#"$REPO_ROOT"/}" \
    "${BROWSER_DIR#"$REPO_ROOT"/}"
  exit 0
fi

# --clean builds from nothing rather than over whatever is there. Each stage already
# clears its own directory, so this only matters when a stage or a file has been RENAMED
# and the old one would otherwise survive to be packaged.
if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$RUNTIME_DIR"
fi

require_dir() {
  [ -d "$1" ] || { echo "Missing $2: $1" >&2; exit 1; }
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required to build the CAD Viewer client." >&2
    exit 1
  fi
}

# --- the CAD Viewer client -----------------------------------------------------------
# The COMMITTED lockfile decides the package manager, not what happens to be installed
# on this machine: pnpm and npm lay out node_modules differently, so the same source
# revision could otherwise be bundled against a different tree. An explicit
# CAD_VIEWER_PACKAGE_MANAGER still wins.
resolve_viewer_package_manager() {
  if [ -n "${VIEWER_PACKAGE_MANAGER:-}" ]; then
    echo "$VIEWER_PACKAGE_MANAGER"
    return
  fi
  if [ -f "$REPO_ROOT/package-lock.json" ]; then
    echo "npm"
    return
  fi
  if [ -f "$VIEWER_APP_DIR/pnpm-lock.yaml" ]; then
    echo "pnpm"
    return
  fi
  if command -v pnpm >/dev/null 2>&1; then
    echo "pnpm"
    return
  fi
  echo "npm"
}

build_viewer_client() {
  local target="$1" package_manager
  # Node builds the client; it is not a runtime requirement of the wheel.
  require_command node
  require_command rsync
  [ -f "$VIEWER_APP_DIR/package.json" ] || { echo "Missing viewer app: $VIEWER_APP_DIR" >&2; exit 1; }
  package_manager="$(resolve_viewer_package_manager)"
  require_command "$package_manager"
  # A plain production build: no sourcemaps. They were 17 MB of a 22 MB runtime for a
  # debugging session that happens in this repo, not inside an installed wheel. The
  # rsync below also excludes *.map, so a dist built WITH maps still bundles clean.
  case "$package_manager" in
    pnpm) CI=true pnpm --dir "$VIEWER_APP_DIR" run build ;;
    npm)  npm --prefix "$VIEWER_APP_DIR" run build ;;
    *)
      echo "Unsupported CAD Viewer package manager: $package_manager" >&2
      echo "Set CAD_VIEWER_PACKAGE_MANAGER to pnpm or npm." >&2
      exit 1
      ;;
  esac
  if [ ! -f "$VIEWER_APP_DIR/dist/index.html" ]; then
    echo "Missing viewer production bundle: $VIEWER_APP_DIR/dist/index.html" >&2
    exit 1
  fi
  rm -rf "$target"
  mkdir -p "$target"
  rsync -a --delete --exclude "*.map" "$VIEWER_APP_DIR/dist/" "$target/"
}

# --- third-party notices --------------------------------------------------------------
# The builders and the browser bundle inline three and meshoptimizer. Shipping
# them inside a wheel is redistribution, and all three are MIT: the licence text has to
# travel with the copy. esbuild keeps the per-file banners (--legal-comments=eof); this is
# the human-readable summary beside them.
write_third_party_notices() {
  local target="$1"
  cat > "$target/THIRD_PARTY_LICENSES.txt" <<'EOF'
The JavaScript in this directory is bundled output. It inlines third-party code:

  three          (MIT)  https://github.com/mrdoob/three.js
  meshoptimizer  (MIT)  https://github.com/zeux/meshoptimizer

Each bundle carries the originating licence banners at end of file
(esbuild --legal-comments=eof). Exact versions are pinned by
package-lock.json at the commit that produced these files.

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
}

build_all() {
  local root="$1"
  if [ "$STAGE_NODE" -eq 1 ]; then
    ensure_node_builder_deps
    bundle_node_builders "$root/node" "${BUILDER_ENTRIES[@]}"
    write_third_party_notices "$root/node"
    echo "Bundled ${root#"$REPO_ROOT"/}/node"
  fi
  if [ "$STAGE_BROWSER" -eq 1 ]; then
    ensure_snapshot_runtime_deps "$SNAPSHOT_BUILD_DEPS_DIR" 1
    build_snapshot_runtime "$root/browser" "$SNAPSHOT_BUILD_DEPS_DIR"
    write_third_party_notices "$root/browser"
    echo "Bundled ${root#"$REPO_ROOT"/}/browser"
  fi
  if [ "$STAGE_VIEWER" -eq 1 ] && [ "$MODE" != "check" ]; then
    build_viewer_client "$root/viewer"
    echo "Bundled ${root#"$REPO_ROOT"/}/viewer"
  fi
}

mkdir -p "$RUNTIME_DIR"
build_all "$RUNTIME_DIR"

if [ "$MODE" = "check" ]; then
  missing=0
  check_stage_outputs() {
    local stage="$1"
    shift
    local name gaps=0
    for name in "$@"; do
      if [ ! -f "$RUNTIME_DIR/$stage/$name" ]; then
        echo "Missing runtime output: packages/cadgen/src/cadgen/_runtime/$stage/$name" >&2
        gaps=1
        missing=1
      fi
    done
    if [ "$gaps" -eq 0 ]; then
      echo "packages/cadgen/src/cadgen/_runtime/$stage built ($# files)."
    fi
  }
  if [ "$STAGE_NODE" -eq 1 ]; then
    check_stage_outputs node "${NODE_OUTPUTS[@]}"
  fi
  if [ "$STAGE_BROWSER" -eq 1 ]; then
    check_stage_outputs browser "${BROWSER_OUTPUTS[@]}"
  fi
  if [ "$missing" -ne 0 ]; then
    echo "" >&2
    echo "The bundler ran but did not produce everything cadgen needs. This is a bundler" >&2
    echo "or dependency failure, not a stale checkout: rerun scripts/bundle/bundle.sh --clean" >&2
    echo "and read the esbuild output above." >&2
    exit 1
  fi
  echo "cadgen packaged runtime builds and is complete."
fi
