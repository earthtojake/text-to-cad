#!/usr/bin/env bash
# Shared helpers for bundling cadgen's Node builders into the packaged runtime
# (packages/cadgen/src/cadgen/_runtime/node). Sourced by scripts/bundle/cadgen-runtime.sh.
#
# cadgen bakes the DXF mesh and the mesh exports by spawning a Node child
# (packages/cadgen/src/cadgen/_internal/node_runtime.py). The builders live in
# packages/cadgen-js/bin and import three and meshoptimizer -- a dependency GRAPH, not just
# a file -- and the wheel ships no node_modules, so each builder is esbuild-bundled into ONE
# self-contained --platform=node file, exactly as snapshot_runtime.sh does for the browser
# bundle. cadgen.assets resolves the result inside the distribution; a checkout resolves
# the real packages/cadgen-js sources instead.
#
# Source it after setting BUNDLE_REPO_ROOT, then call bundle_node_builders /
# check_node_builders with the builder entry files.
#
# shellcheck shell=bash

# Pinned so the committed bundles are reproducible. three and
# meshoptimizer are read from packages/cadgen-js/package-lock.json, the one place their exact
# versions are already pinned, so a dependency bump cannot silently change what ships without
# also changing the committed bundle.
NODE_BUILDER_ESBUILD_VERSION="${NODE_BUILDER_ESBUILD_VERSION:-0.27.7}"
NODE_BUILDER_BUILD_DEPS_DIR="${NODE_BUILDER_BUILD_DEPS_DIR:-${BUNDLE_REPO_ROOT:?BUNDLE_REPO_ROOT must be set before sourcing node_builders.sh}/tmp/node-builder-build}"
NODE_BUILDER_LOCKFILE="$BUNDLE_REPO_ROOT/packages/cadgen-js/package-lock.json"

node_builder_locked_version() {
  local name="$1"
  node -p "
    const lock = require('$NODE_BUILDER_LOCKFILE');
    const entry = lock.packages && lock.packages['node_modules/$name'];
    if (!entry || !entry.version) {
      throw new Error('packages/cadgen-js/package-lock.json has no pinned $name');
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
  # Mark the emitted directory as ESM, matching packages/cadgen-js itself, so a builder emitted
  # as a bare `.js` still parses as a module rather than as CommonJS.
  printf '%s\n' '{ "type": "module" }' > "$out_dir/package.json"
  for entry in "$@"; do
    if [ ! -f "$entry" ]; then
      echo "Missing Node builder source: $entry" >&2
      return 1
    fi
    basename_out="$(basename "$entry")"
    # NODE_PATH resolves the builders' remaining bare specifiers (three, meshoptimizer)
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
      --legal-comments=eof \
      --outfile="$out_dir/$basename_out" || return 1
    node_builder_assert_not_empty "$out_dir/$basename_out" "$entry" || return 1
  done
}

# A builder whose whole job is a side effect can be tree-shaken to NOTHING and esbuild will
# not fail: a re-export-only entry emitted a 20-byte shebang because the package's
# package.json `sideEffects` list did not name the script. esbuild says so in a note, but the
# build succeeds, the file exists, and every other check passes -- the only symptom would be
# a builder that runs and does nothing.
#
# A raw size floor is the wrong test: a legitimate builder can be a few hundred bytes. What
# is never legitimate is emitting no CODE, so strip the shebang and check what is left.
NODE_BUILDER_MIN_CODE_BYTES="${NODE_BUILDER_MIN_CODE_BYTES:-32}"

node_builder_assert_not_empty() {
  local emitted="$1" entry="$2" code_bytes
  code_bytes="$(sed '1{/^#!/d;}' "$emitted" | tr -d '[:space:]' | wc -c | tr -d '[:space:]')"
  if [ "$code_bytes" -lt "$NODE_BUILDER_MIN_CODE_BYTES" ]; then
    echo "Node builder bundled to $code_bytes bytes of code, which cannot be a working builder:" >&2
    echo "  entry:   $entry" >&2
    echo "  emitted: $emitted" >&2
    echo "esbuild tree-shakes a side-effect-only import unless the package's \`sideEffects\`" >&2
    echo "field names the file. Add the entry there, or import a binding it actually uses." >&2
    return 1
  fi
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
