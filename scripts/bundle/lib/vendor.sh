#!/usr/bin/env bash
# Shared vendoring helpers for the bundle scripts.
#
# A skill must be self-contained at runtime (AGENTS.md), so shared Python packages
# under packages/<pkg> are VENDORED into each consuming skill's runtime. The copy
# rules (which files to drop, how to detect staleness) were duplicated across every
# bundle-<skill>.sh; this library is the single source of truth.
#
# Source it, then either:
#   * call vendor_python_skill --skill <id> --package <pkg> "$@"   (whole script), or
#   * call vendor_python_package / check_python_runtime directly   (inside a larger
#     bundle that also builds JS, e.g. cad / cad-viewer).
#
# shellcheck shell=bash

# Canonical exclude list for vendoring a Python source package into a skill
# runtime: caches, build artifacts, docs, and tests — never runtime code.
BUNDLE_PY_EXCLUDES=(
  __pycache__
  .pytest_cache
  '*.pyc'
  '*.egg-info'
  '*.md'
  build
  dist
  tests
  __tests__
  'test_*.py'
  '*_test.py'
)

# Pre-expand the exclude patterns into rsync (--exclude X) and diff (-x X) flag
# arrays once at source time. Plain loops (no mapfile) so this works on the
# bash 3.2 shipped with macOS as well as the bash 4+/5 in CI.
BUNDLE_PY_RSYNC_EXCLUDES=()
BUNDLE_PY_DIFF_EXCLUDES=()
_bundle_pattern=""
for _bundle_pattern in "${BUNDLE_PY_EXCLUDES[@]}"; do
  BUNDLE_PY_RSYNC_EXCLUDES+=(--exclude "$_bundle_pattern")
  BUNDLE_PY_DIFF_EXCLUDES+=(-x "$_bundle_pattern")
done
unset _bundle_pattern

# require_python_package <package_dir> <module_name>
# Fail unless <package_dir> is a real Python package source (pyproject + src/<module>).
require_python_package() {
  local package_dir="$1" module="$2"
  if [ ! -f "$package_dir/pyproject.toml" ] || [ ! -d "$package_dir/src/$module" ]; then
    echo "Missing $module package source: $package_dir" >&2
    return 1
  fi
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync is required to vendor $module into a skill runtime." >&2
    return 1
  fi
}

# vendor_python_package <package_dir> <target_dir>
# Mirror <package_dir> into <target_dir>, dropping BUNDLE_PY_EXCLUDES.
vendor_python_package() {
  local package_dir="$1" target_dir="$2"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  rsync -a --delete --delete-excluded "${BUNDLE_PY_RSYNC_EXCLUDES[@]}" "$package_dir/" "$target_dir/"
}

# check_python_runtime <package_dir> <committed_runtime_dir> <check_tmp_dir> <label> <fix_hint>
# Re-vendor to a tmp dir and fail if the committed runtime differs (ignoring the
# excluded extras, so a development symlink to the full package source still matches).
check_python_runtime() {
  local package_dir="$1" committed_dir="$2" check_dir="$3" label="$4" fix_hint="$5"
  if [ ! -d "$committed_dir" ]; then
    echo "Missing generated runtime: $label" >&2
    echo "$fix_hint" >&2
    return 1
  fi
  vendor_python_package "$package_dir" "$check_dir"
  local diff_path="${TMPDIR:-/tmp}/bundle-vendor-diff.txt"
  if ! diff -qr "${BUNDLE_PY_DIFF_EXCLUDES[@]}" "$check_dir" "$committed_dir" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "$label is stale." >&2
    echo "$fix_hint" >&2
    return 1
  fi
  echo "$label is up to date."
}

# vendor_python_skill --skill <id> --package <pkg> [--module <name>] [--check] [--clean] [args...]
# The whole body of a single-package vendoring bundle script (dxf, sdf, srdf, urdf).
# <module> defaults to <pkg>. Vendors packages/<pkg> -> skills/<id>/scripts/packages/<pkg>.
vendor_python_skill() {
  local repo_root skill="" package="" module="" mode="write" clean=0 print_outputs=0
  repo_root="${BUNDLE_REPO_ROOT:?BUNDLE_REPO_ROOT must be set before vendor_python_skill}"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --skill) skill="$2"; shift 2 ;;
      --package) package="$2"; shift 2 ;;
      --module) module="$2"; shift 2 ;;
      --check) mode="check"; shift ;;
      --clean) clean=1; shift ;;
      --print-outputs) print_outputs=1; shift ;;
      -h|--help)
        echo "Usage: bundle-skill.sh $skill [--check] [--clean] [--print-outputs]" >&2
        echo "Vendors packages/$package into skills/$skill/scripts/packages/$package." >&2
        return 0 ;;
      *) echo "Unknown argument: $1" >&2; return 2 ;;
    esac
  done
  [ -n "$skill" ] && [ -n "$package" ] || { echo "vendor_python_skill needs --skill and --package" >&2; return 2; }
  [ -n "$module" ] || module="$package"

  local package_dir="$repo_root/packages/$package"
  local runtime_dir="$repo_root/skills/$skill/scripts/packages/$package"
  local check_dir="${BUNDLE_CHECK_DIR:-$repo_root/tmp/$skill-skill-runtime-check}/packages/$package"
  local rel_runtime="skills/$skill/scripts/packages/$package"
  local fix_hint="Run scripts/bundle/bundle-skill.sh $skill and commit $rel_runtime."

  # Answer scripts/github-workflows/check-builds.sh before doing any work, so the
  # generated-path list is derived from the bundle scripts instead of repeated there.
  if [ "$print_outputs" -eq 1 ]; then
    printf '%s\n' "$rel_runtime"
    return 0
  fi

  require_python_package "$package_dir" "$module" || return 1
  [ "$clean" -eq 1 ] && rm -rf "${check_dir%/packages/$package}"

  if [ "$mode" = "check" ]; then
    check_python_runtime "$package_dir" "$runtime_dir" "$check_dir" "$rel_runtime" "$fix_hint"
  else
    vendor_python_package "$package_dir" "$runtime_dir"
    echo "Bundled $rel_runtime"
  fi
}
