#!/usr/bin/env bash
# Shared helpers for shipping cadgen's Node builders inside a skill runtime.
#
# cadgen builds the implicit and DXF render packages by spawning a Node child
# (packages/cadgen/src/cadgen/_internal/node_runtime.py). The builders themselves live in
# packages/cadjs/bin and import three, meshoptimizer and implicitjs -- a dependency GRAPH,
# not just a file. A published skill ships no node_modules (design
# §4.5, "Node the binary is available; the dependency graph is not"), so the builders are
# esbuild-bundled into ONE self-contained --platform=node file each, exactly as
# scripts/bundle/skills/bundle-cad.sh does for snapshot-render.js.
#
# The outputs land at <skill>/scripts/packages/cadjs/bin/<name>, which is the path
# `node_builder_script()` already derives (node_package_root() is cadgen's own
# parents[4] -- packages/ in the dev checkout, <skill>/scripts/packages/ in a vendored
# runtime). Nothing in the Python side changes, and the dev checkout keeps resolving the
# real packages/cadjs/bin sources through the cadgen symlink.
#
# Source it after setting BUNDLE_REPO_ROOT, then call bundle_node_builders /
# check_node_builders with the entry files the skill's builders need.
#
# shellcheck shell=bash

# Pinned so the committed bundles are reproducible. esbuild matches bundle-cad.sh; three and
# meshoptimizer are read from packages/cadjs/package-lock.json, the one place their exact
# versions are already pinned, so a dependency bump cannot silently change what ships without
# also changing the committed bundle.
NODE_BUILDER_ESBUILD_VERSION="${NODE_BUILDER_ESBUILD_VERSION:-0.27.7}"
NODE_BUILDER_BUILD_DEPS_DIR="${NODE_BUILDER_BUILD_DEPS_DIR:-${BUNDLE_REPO_ROOT:?BUNDLE_REPO_ROOT must be set before sourcing node_builders.sh}/tmp/node-builder-build}"
NODE_BUILDER_LOCKFILE="$BUNDLE_REPO_ROOT/packages/cadjs/package-lock.json"

# Files whose runtime paths are computed from `import.meta.url` inside the bundle, so they
# cannot be inlined and must be emitted BESIDE it under the same basename:
#   implicitClosureHooks.mjs  <- register("./implicitClosureHooks.mjs", import.meta.url)
#   meshWorkerEntry.js        <- new Worker(new URL("./meshWorkerEntry.js", import.meta.url))
# Every other import in both builder graphs is a plain static import and gets inlined.

node_builder_locked_version() {
  local name="$1"
  node -p "
    const lock = require('$NODE_BUILDER_LOCKFILE');
    const entry = lock.packages && lock.packages['node_modules/$name'];
    if (!entry || !entry.version) {
      throw new Error('packages/cadjs/package-lock.json has no pinned $name');
    }
    entry.version;
  "
}

node_builder_require_tools() {
  local tool
  for tool in node npm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "$tool is required to bundle cadgen's Node builders." >&2
      return 1
    fi
  done
  if [ ! -f "$NODE_BUILDER_LOCKFILE" ]; then
    echo "Missing $NODE_BUILDER_LOCKFILE; the builder bundle reads its pinned deps from it." >&2
    return 1
  fi
}

# ensure_node_builder_deps
# Install the pinned build toolchain into tmp/, reusing it when it is already correct.
ensure_node_builder_deps() {
  node_builder_require_tools || return 1
  local three meshoptimizer
  three="$(node_builder_locked_version three)" || return 1
  meshoptimizer="$(node_builder_locked_version meshoptimizer)" || return 1

  if [ -x "$NODE_BUILDER_BUILD_DEPS_DIR/node_modules/.bin/esbuild" ] && node -e "
    const deps = {
      esbuild: '$NODE_BUILDER_ESBUILD_VERSION',
      three: '$three',
      meshoptimizer: '$meshoptimizer',
    };
    for (const [name, expected] of Object.entries(deps)) {
      const actual = require('$NODE_BUILDER_BUILD_DEPS_DIR/node_modules/' + name + '/package.json').version;
      if (actual !== expected) process.exit(1);
    }
  " 2>/dev/null; then
    return 0
  fi

  mkdir -p "$NODE_BUILDER_BUILD_DEPS_DIR"
  npm install --prefix "$NODE_BUILDER_BUILD_DEPS_DIR" --no-audit --no-fund \
    --fetch-retries=1 --fetch-timeout=10000 \
    "esbuild@$NODE_BUILDER_ESBUILD_VERSION" \
    "three@$three" \
    "meshoptimizer@$meshoptimizer"
}

# bundle_node_builders <out_bin_dir> <entry_file>...
# Bundle each entry into <out_bin_dir>/<basename>, self-contained.
bundle_node_builders() {
  local out_dir="$1"
  shift
  local entry basename_out
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  # meshWorkerEntry.js is spawned by basename, and a bare .js with no `type` above it parses
  # as CommonJS. This marks the emitted directory as ESM, matching packages/cadjs itself.
  printf '%s\n' '{ "type": "module" }' > "$out_dir/package.json"
  for entry in "$@"; do
    if [ ! -f "$entry" ]; then
      echo "Missing Node builder source: $entry" >&2
      return 1
    fi
    basename_out="$(basename "$entry")"
    # NODE_PATH resolves the bare `implicitjs/...` specifiers through implicitjs's exports
    # map and the pinned three/meshoptimizer out of the tmp toolchain, so the bundle is
    # hermetic on a fresh checkout with no packages/*/node_modules. A directory --alias
    # cannot do the first: it bypasses the exports map.
    NODE_PATH="$BUNDLE_REPO_ROOT/packages:$NODE_BUILDER_BUILD_DEPS_DIR/node_modules" \
      "$NODE_BUILDER_BUILD_DEPS_DIR/node_modules/.bin/esbuild" "$entry" \
      --bundle \
      --format=esm \
      --platform=node \
      --target=node20 \
      --main-fields=module,main \
      --minify \
      --keep-names \
      --legal-comments=none \
      --outfile="$out_dir/$basename_out" || return 1
  done
}

# check_node_builders <committed_bin_dir> <check_bin_dir> <label> <fix_hint> <entry_file>...
# Rebuild into <check_bin_dir> and fail if the committed bundles differ. Runs in BOTH
# layouts: the bundles are esbuild output from packages/ source, never a symlink, so the
# development layout has nothing to opt out of here.
check_node_builders() {
  local committed_dir="$1" check_dir="$2" label="$3" fix_hint="$4"
  shift 4
  if [ ! -d "$committed_dir" ]; then
    echo "Missing generated Node builders: $label" >&2
    echo "$fix_hint" >&2
    return 1
  fi
  bundle_node_builders "$check_dir" "$@" || return 1
  local diff_path="${TMPDIR:-/tmp}/bundle-node-builders-diff.txt"
  if ! diff -qr "$check_dir" "$committed_dir" >"$diff_path"; then
    cat "$diff_path" >&2
    echo "" >&2
    echo "$label is stale." >&2
    echo "$fix_hint" >&2
    return 1
  fi
  echo "$label is up to date."
}
