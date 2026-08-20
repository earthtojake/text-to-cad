#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export BUNDLE_REPO_ROOT="$REPO_ROOT"
# shellcheck source=../lib/vendor.sh
source "$SCRIPT_DIR/../lib/vendor.sh"
# shellcheck source=../lib/snapshot_runtime.sh
source "$SCRIPT_DIR/../lib/snapshot_runtime.sh"

MODE="write"
CLEAN=0
PRINT_OUTPUTS=0

CADGEN_PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
CADGEN_RUNTIME_DIR="$REPO_ROOT/skills/urdf/scripts/packages/cadgen"
SNAPSHOT_RUNTIME_DIR="$REPO_ROOT/skills/urdf/scripts/snapshot/runtime"
CHECK_DIR="${URDF_SKILL_BUNDLE_CHECK_DIR:-$REPO_ROOT/tmp/urdf-skill-runtime-check}"
# The SAME cadjs entrypoint every rendering skill bundles, so a robot snapshot and the CAD
# Viewer are the same picture. A separate npm scratch dir only so skills can build
# concurrently.
SNAPSHOT_BUILD_DEPS_DIR="${URDF_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/urdf-snapshot-build}"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh urdf [--check] [--clean]

Bundles the URDF skill runtime: the vendored cadgen Python package and the
self-contained headless render runtime its snapshot CLI drives.

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
  printf '%s\n' "skills/urdf/scripts/packages/cadgen"
  printf '%s\n' "skills/urdf/scripts/snapshot/runtime"
  exit 0
fi

require_python_package "$CADGEN_PACKAGE_DIR" cadgen
ensure_snapshot_runtime_deps "$SNAPSHOT_BUILD_DEPS_DIR" 1

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR"
fi

# The snapshot runtime is esbuild output, never a symlink, so it is checked in BOTH
# layouts -- unlike the vendored cadgen copy, which the development layout replaces with a
# link to its source.
check_snapshot() {
  build_snapshot_runtime "$CHECK_DIR/snapshot-runtime" "$SNAPSHOT_BUILD_DEPS_DIR"
  check_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$CHECK_DIR/snapshot-runtime" \
    "skills/urdf/scripts/snapshot/runtime" \
    "Run scripts/bundle/bundle-skill.sh urdf and commit skills/urdf/scripts/snapshot/runtime."
}

if [ "$MODE" = "check" ] && [ -L "$CADGEN_RUNTIME_DIR" ]; then
  rm -rf "$CHECK_DIR"
  check_snapshot || exit 1
  "$REPO_ROOT/scripts/dev/setup-skill-symlink.sh" urdf --check
  echo "URDF skill is in development symlink layout; production package freshness is checked on build-test/main."
  exit 0
fi

if [ "$MODE" = "check" ]; then
  rm -rf "$CHECK_DIR"
  stale=0
  check_python_runtime "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR" \
    "$CHECK_DIR/packages/cadgen" "skills/urdf/scripts/packages/cadgen" \
    "Run scripts/bundle/bundle-skill.sh urdf and commit the updated production package copy." \
    || stale=1
  check_snapshot || stale=1
  if [ "$stale" -ne 0 ]; then
    echo "" >&2
    echo "Run scripts/bundle/bundle-skill.sh urdf and commit the updated production outputs." >&2
    exit 1
  fi
  echo "URDF skill production outputs are up to date."
else
  vendor_python_package "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR"
  echo "Bundled skills/urdf/scripts/packages/cadgen"
  build_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$SNAPSHOT_BUILD_DEPS_DIR"
  echo "Bundled skills/urdf/scripts/snapshot/runtime"
fi
