#!/usr/bin/env bash
set -euo pipefail

# Vendors packages/cadgen into skills/dxf/scripts/packages/cadgen, and esbuilds the Node
# drawing-preview builder into skills/dxf/scripts/packages/cadjs/bin. The builder is what
# `cadgen._internal.drawing_package` spawns to bake preview.glb; it lives in
# packages/cadjs/bin and imports three, meshoptimizer and implicitjs, none of which a
# published skill ships as node_modules -- so it is bundled self-contained (design §4.5).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export BUNDLE_REPO_ROOT="$REPO_ROOT"
# shellcheck source=../lib/vendor.sh
source "$SCRIPT_DIR/../lib/vendor.sh"
# shellcheck source=../lib/node_builders.sh
source "$SCRIPT_DIR/../lib/node_builders.sh"
# shellcheck source=../lib/snapshot_runtime.sh
source "$SCRIPT_DIR/../lib/snapshot_runtime.sh"

MODE="write"
CLEAN=0
PRINT_OUTPUTS=0

CADGEN_PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
CADGEN_RUNTIME_DIR="$REPO_ROOT/skills/dxf/scripts/packages/cadgen"
BUILDERS_RUNTIME_DIR="$REPO_ROOT/skills/dxf/scripts/packages/cadjs/bin"
BUILDER_ENTRIES=("$REPO_ROOT/packages/cadjs/bin/dxf-artifact.mjs")
SNAPSHOT_RUNTIME_DIR="$REPO_ROOT/skills/dxf/scripts/snapshot/runtime"
CHECK_DIR="${DXF_SKILL_BUNDLE_CHECK_DIR:-$REPO_ROOT/tmp/dxf-skill-runtime-check}"
# Shared with the CAD skill so both build the identical browser bundle; separate
# npm scratch dir only so the two skills can bundle concurrently.
SNAPSHOT_BUILD_DEPS_DIR="${DXF_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/dxf-snapshot-build}"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh dxf [--check] [--clean]

Bundles the DXF skill runtime: the vendored cadgen Python package and the
self-contained Node drawing-preview builder.

Options:
  --check  Bundle into tmp/ and fail if checked-in production outputs are stale.
  --clean  Remove temporary check directories first.
  --print-outputs
           Print the repo-relative generated output paths, then exit.
  -h, --help
           Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --clean) CLEAN=1 ;;
    --print-outputs) PRINT_OUTPUTS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$PRINT_OUTPUTS" -eq 1 ]; then
  printf '%s\n' "${CADGEN_RUNTIME_DIR#"$REPO_ROOT"/}"
  printf '%s\n' "${BUILDERS_RUNTIME_DIR#"$REPO_ROOT"/}"
  printf '%s\n' "${SNAPSHOT_RUNTIME_DIR#"$REPO_ROOT"/}"
  exit 0
fi

require_python_package "$CADGEN_PACKAGE_DIR" cadgen
ensure_node_builder_deps
# --clean BEFORE the install, not after. Reversed, this deleted the very directory it had
# just installed esbuild into, and the build below then died with exit 127 looking for it --
# which is what `scripts/bundle/bundle.sh --clean` does in CI. bundle-cad.sh has always had
# this order; dxf did not.
if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR" "$SNAPSHOT_BUILD_DEPS_DIR"
fi

ensure_snapshot_runtime_deps "$SNAPSHOT_BUILD_DEPS_DIR" 1

if [ "$MODE" = "check" ]; then
  rm -rf "$CHECK_DIR"
  stale=0
  check_python_runtime \
    "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR" "$CHECK_DIR/packages/cadgen" \
    "skills/dxf/scripts/packages/cadgen" \
    "Run scripts/bundle/bundle-skill.sh dxf and commit skills/dxf/scripts/packages/cadgen." \
    || stale=1
  check_node_builders \
    "$BUILDERS_RUNTIME_DIR" "$CHECK_DIR/packages/cadjs/bin" \
    "skills/dxf/scripts/packages/cadjs/bin" \
    "Run scripts/bundle/bundle-skill.sh dxf and commit skills/dxf/scripts/packages/cadjs." \
    "${BUILDER_ENTRIES[@]}" \
    || stale=1
  build_snapshot_runtime "$CHECK_DIR/snapshot-runtime" "$SNAPSHOT_BUILD_DEPS_DIR"
  check_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$CHECK_DIR/snapshot-runtime" \
    "skills/dxf/scripts/snapshot/runtime" \
    "Run scripts/bundle/bundle-skill.sh dxf and commit skills/dxf/scripts/snapshot/runtime." \
    || stale=1
  if [ "$stale" -ne 0 ]; then
    echo "" >&2
    echo "Run scripts/bundle/bundle-skill.sh dxf and commit the updated production outputs." >&2
    exit 1
  fi
  echo "DXF skill production outputs are up to date."
else
  vendor_python_package "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR"
  echo "Bundled skills/dxf/scripts/packages/cadgen"
  bundle_node_builders "$BUILDERS_RUNTIME_DIR" "${BUILDER_ENTRIES[@]}"
  echo "Bundled skills/dxf/scripts/packages/cadjs/bin"
  build_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$SNAPSHOT_BUILD_DEPS_DIR"
  echo "Bundled skills/dxf/scripts/snapshot/runtime"
fi
