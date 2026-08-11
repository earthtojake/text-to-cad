#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export BUNDLE_REPO_ROOT="$REPO_ROOT"
# shellcheck source=../lib/vendor.sh
source "$SCRIPT_DIR/../lib/vendor.sh"
# shellcheck source=../lib/snapshot_runtime.sh
source "$SCRIPT_DIR/../lib/snapshot_runtime.sh"
# shellcheck source=../lib/node_builders.sh
source "$SCRIPT_DIR/../lib/node_builders.sh"

MODE="write"
CLEAN=0
INSTALL_DEPS=1
PRINT_OUTPUTS=0


BUILD_DEPS_DIR="${CAD_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/cad-snapshot-build}"
CHECK_DIR="${CAD_SNAPSHOT_CHECK_DIR:-$REPO_ROOT/tmp/cad-snapshot-runtime-check}"
RUNTIME_DIR="$REPO_ROOT/skills/cad/scripts/snapshot/runtime"
ENTRYPOINT="$REPO_ROOT/packages/cadjs/src/common/headlessRenderEntry.js"
CADPY_PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
CADPY_RUNTIME_DIR="$REPO_ROOT/skills/cad/scripts/packages/cadgen"
# cadgen resolves its Node builders beside whatever runtime ships it, so a runtime that ships
# cadgen must ship the builders cadgen can reach for. `scripts/gen` accepts a bare gen_dxf()
# document, which routes through the shared drawing-package path and shells out to this
# builder -- so the CAD skill needs it even though drawings are the DXF skill's subject.
# Missing here, the failure only appears in the bundled tree: in the development layout the
# lookup walks up to the repo's own packages/cadjs and finds it.
BUILDERS_RUNTIME_DIR="$REPO_ROOT/skills/cad/scripts/packages/cadjs/bin"
BUILDER_ENTRIES=("$REPO_ROOT/packages/cadjs/bin/dxf-artifact.mjs")

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh cad [--check] [--clean] [--no-install]

Bundles the self-contained browser runtime used by skills/cad/scripts/snapshot
and the bundled Python package runtime used by skills/cad/scripts.

Options:
  --check       Bundle into tmp/ and fail if snapshot/runtime is stale.
  --clean       Remove the temporary dependency/build directories first.
  --no-install  Require existing build dependencies in tmp/cad-snapshot-build.
  --print-outputs
                Print the repo-relative generated output paths, then exit.
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
    "${RUNTIME_DIR#"$REPO_ROOT"/}" \
    "${CADPY_RUNTIME_DIR#"$REPO_ROOT"/}" \
    "${BUILDERS_RUNTIME_DIR#"$REPO_ROOT"/}"
  exit 0
fi

if [ ! -f "$ENTRYPOINT" ]; then
  echo "Missing snapshot render entrypoint: $ENTRYPOINT" >&2
  echo "The CAD snapshot runtime is built from the same shared render entrypoint used by CAD Viewer." >&2
  exit 1
fi

if [ ! -f "$CADPY_PACKAGE_DIR/pyproject.toml" ] || [ ! -d "$CADPY_PACKAGE_DIR/src/cadgen" ]; then
  echo "Missing cadgen package source: $CADPY_PACKAGE_DIR" >&2
  echo "The CAD skill Python runtime is bundled from packages/cadgen." >&2
  exit 1
fi

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$BUILD_DEPS_DIR" "$CHECK_DIR"
fi

sync_cadgen_runtime() {
  vendor_python_package "$CADPY_PACKAGE_DIR" "$1"
}

check_cadgen_runtime() {
  check_python_runtime "$CADPY_PACKAGE_DIR" "$CADPY_RUNTIME_DIR" \
    "$CHECK_DIR/packages/cadgen" "skills/cad/scripts/packages/cadgen" \
    "Run scripts/bundle/bundle-skill.sh cad and commit skills/cad/scripts/packages/cadgen."
}

ensure_node_builder_deps
ensure_snapshot_runtime_deps "$BUILD_DEPS_DIR" "$INSTALL_DEPS"

if [ "$MODE" = "check" ]; then
  build_snapshot_runtime "$CHECK_DIR" "$BUILD_DEPS_DIR"
  check_snapshot_runtime "$RUNTIME_DIR" "$CHECK_DIR" \
    "skills/cad/scripts/snapshot/runtime" \
    "Run scripts/bundle/bundle-skill.sh cad and commit the updated runtime files." \
    || exit 1
  echo "CAD snapshot runtime is up to date."
  check_node_builders \
    "$BUILDERS_RUNTIME_DIR" "$CHECK_DIR/packages/cadjs/bin" \
    "skills/cad/scripts/packages/cadjs/bin" \
    "Run scripts/bundle/bundle-skill.sh cad and commit skills/cad/scripts/packages/cadjs/bin." \
    "${BUILDER_ENTRIES[@]}" \
    || exit 1
  echo "skills/cad/scripts/packages/cadjs/bin is up to date."
  check_cadgen_runtime
else
  build_snapshot_runtime "$RUNTIME_DIR" "$BUILD_DEPS_DIR"
  sync_cadgen_runtime "$CADPY_RUNTIME_DIR"
  bundle_node_builders "$BUILDERS_RUNTIME_DIR" "${BUILDER_ENTRIES[@]}"
  echo "Bundled skills/cad/scripts/snapshot/runtime"
  echo "Bundled skills/cad/scripts/packages/cadgen"
  echo "Bundled skills/cad/scripts/packages/cadjs/bin"
fi
