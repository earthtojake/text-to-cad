#!/usr/bin/env bash
set -euo pipefail

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

IMPLICITJS_PACKAGE_DIR="$REPO_ROOT/packages/implicitjs"
IMPLICITJS_RUNTIME_DIR="$REPO_ROOT/skills/implicit-cad/scripts/packages/implicitjs"
# scripts/gen drives cadgen.implicit_artifact, so the skill vendors the Python package the
# same way `cad` and `dxf` do.
CADGEN_PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
CADGEN_RUNTIME_DIR="$REPO_ROOT/skills/implicit-cad/scripts/packages/cadgen"
# The Node BUILDER cadgen spawns. It lives in packages/cadjs and imports meshoptimizer and
# implicitjs, so it is esbuilt self-contained rather than copied (design §4.5). Two of its
# three entries exist only because their runtime path is computed from `import.meta.url`
# inside the bundle and therefore cannot be inlined: implicitClosureHooks.mjs is
# `register()`-ed by name, and meshWorkerEntry.js is the worker_threads entry
# implicitjs/lib/implicitCad/meshWorkers.js spawns.
BUILDERS_RUNTIME_DIR="$REPO_ROOT/skills/implicit-cad/scripts/packages/cadjs/bin"
BUILDER_ENTRIES=(
  "$REPO_ROOT/packages/cadjs/bin/implicit-artifact.mjs"
  "$REPO_ROOT/packages/cadjs/bin/implicitClosureHooks.mjs"
  "$REPO_ROOT/packages/implicitjs/src/lib/implicitCad/meshWorkerEntry.js"
)
# The headless browser runtime the snapshot CLI drives. Built from the SAME cadjs
# entrypoint the CAD Viewer and every other rendering skill use, so an implicit snapshot and
# the viewport are the same picture by construction. A skill may not reach into another
# skill's files, so each gets its own generated copy.
SNAPSHOT_RUNTIME_DIR="$REPO_ROOT/skills/implicit-cad/scripts/snapshot/runtime"
SNAPSHOT_BUILD_DEPS_DIR="${IMPLICIT_CAD_SNAPSHOT_BUILD_DEPS_DIR:-$REPO_ROOT/tmp/implicit-cad-snapshot-build}"
CHECK_DIR="${IMPLICIT_CAD_SKILL_BUNDLE_CHECK_DIR:-$REPO_ROOT/tmp/implicit-cad-skill-runtime-check}"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh implicit-cad [--check] [--clean]

Bundles the implicitjs package copy used by skills/implicit-cad in production
layouts.

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
    --check)
      MODE="check"
      ;;
    --clean)
      CLEAN=1
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
  printf '%s\n' "${IMPLICITJS_RUNTIME_DIR#"$REPO_ROOT"/}"
  printf '%s\n' "${CADGEN_RUNTIME_DIR#"$REPO_ROOT"/}"
  printf '%s\n' "${BUILDERS_RUNTIME_DIR#"$REPO_ROOT"/}"
  printf '%s\n' "${SNAPSHOT_RUNTIME_DIR#"$REPO_ROOT"/}"
  exit 0
fi

require_file() {
  local path_to_check="$1"
  local label="$2"
  if [ ! -f "$path_to_check" ]; then
    echo "Missing $label: $path_to_check" >&2
    exit 1
  fi
}

require_dir() {
  local path_to_check="$1"
  local label="$2"
  if [ ! -d "$path_to_check" ]; then
    echo "Missing $label: $path_to_check" >&2
    exit 1
  fi
}

sync_implicitjs_package() {
  local target_dir="$1"
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

check_implicitjs_package() {
  local expected_dir="$CHECK_DIR/packages/implicitjs"
  local label="${IMPLICITJS_RUNTIME_DIR#$REPO_ROOT/}"
  local diff_path="${TMPDIR:-/tmp}/implicit-cad-skill-implicitjs-package-diff.txt"
  if [ ! -d "$IMPLICITJS_RUNTIME_DIR" ]; then
    echo "Missing generated implicitjs package runtime: $label" >&2
    return 1
  fi
  if ! diff -qr \
    -x node_modules \
    -x dist \
    -x coverage \
    -x tmp \
    -x .vite \
    -x .DS_Store \
    "$expected_dir" "$IMPLICITJS_RUNTIME_DIR" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "Implicit CAD skill implicitjs package runtime is stale." >&2
    return 1
  fi
  return 0
}

check_development_layout() {
  "$REPO_ROOT/scripts/dev/setup-skill-symlink.sh" implicit-cad --check
  echo "Implicit CAD skill is in development symlink layout; production package freshness is checked on build-test/main."
}

require_file "$IMPLICITJS_PACKAGE_DIR/package.json" "implicitjs package"
require_dir "$IMPLICITJS_PACKAGE_DIR/src" "implicitjs source"
require_file "$REPO_ROOT/skills/implicit-cad/scripts/snapshot/__main__.py" "implicit CAD snapshot CLI"
require_file "$IMPLICITJS_PACKAGE_DIR/scripts/export.mjs" "implicit CAD export CLI"
require_python_package "$CADGEN_PACKAGE_DIR" cadgen
ensure_node_builder_deps
ensure_snapshot_runtime_deps "$SNAPSHOT_BUILD_DEPS_DIR" 1

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR"
fi

# The node BUILDERS are tracked on develop, so they are checked in BOTH layouts -- they are
# esbuild output, never a symlink, and a stale one would ship. The vendored package copies
# below are not: the development layout deliberately replaces those with links to sources.
check_builders() {
  check_node_builders \
    "$BUILDERS_RUNTIME_DIR" "$CHECK_DIR/packages/cadjs/bin" \
    "skills/implicit-cad/scripts/packages/cadjs/bin" \
    "Run scripts/bundle/bundle-skill.sh implicit-cad and commit skills/implicit-cad/scripts/packages/cadjs." \
    "${BUILDER_ENTRIES[@]}"
}

# The snapshot runtime is tracked and checked the same way, exactly as `cad` and `dxf` track
# theirs. It was briefly gitignored here and "published from build-test/main" instead --
# which nothing did: the publish job stages with `git add -A`, so an ignored path never
# reached main at all, and the shipped skill sat in Playwright for the full 300s timeout
# with no render.html to load.
check_snapshot() {
  build_snapshot_runtime "$CHECK_DIR/snapshot-runtime" "$SNAPSHOT_BUILD_DEPS_DIR"
  check_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$CHECK_DIR/snapshot-runtime" \
    "skills/implicit-cad/scripts/snapshot/runtime" \
    "Run scripts/bundle/bundle-skill.sh implicit-cad and commit skills/implicit-cad/scripts/snapshot/runtime."
}

if [ "$MODE" = "check" ] && [ -L "$IMPLICITJS_RUNTIME_DIR" ]; then
  rm -rf "$CHECK_DIR"
  stale=0
  check_builders || stale=1
  check_snapshot || stale=1
  [ "$stale" -eq 0 ] || exit 1
  check_development_layout
  exit 0
fi

if [ "$MODE" = "check" ]; then
  rm -rf "$CHECK_DIR"
  sync_implicitjs_package "$CHECK_DIR/packages/implicitjs"

  stale=0
  check_implicitjs_package || stale=1
  check_builders || stale=1
  check_snapshot || stale=1
  check_python_runtime \
    "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR" "$CHECK_DIR/packages/cadgen" \
    "skills/implicit-cad/scripts/packages/cadgen" \
    "Run scripts/bundle/bundle-skill.sh implicit-cad and commit skills/implicit-cad/scripts/packages/cadgen." \
    || stale=1

  if [ "$stale" -ne 0 ]; then
    echo "" >&2
    echo "Run scripts/bundle/bundle-skill.sh implicit-cad and commit the updated production package copy." >&2
    exit 1
  fi
  echo "Implicit CAD skill production outputs are up to date."
else
  sync_implicitjs_package "$IMPLICITJS_RUNTIME_DIR"
  echo "Bundled skills/implicit-cad/scripts/packages/implicitjs"
  vendor_python_package "$CADGEN_PACKAGE_DIR" "$CADGEN_RUNTIME_DIR"
  echo "Bundled skills/implicit-cad/scripts/packages/cadgen"
  bundle_node_builders "$BUILDERS_RUNTIME_DIR" "${BUILDER_ENTRIES[@]}"
  echo "Bundled skills/implicit-cad/scripts/packages/cadjs/bin"
  build_snapshot_runtime "$SNAPSHOT_RUNTIME_DIR" "$SNAPSHOT_BUILD_DEPS_DIR"
  echo "Bundled skills/implicit-cad/scripts/snapshot/runtime"
fi
