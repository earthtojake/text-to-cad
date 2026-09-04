#!/usr/bin/env bash
# Builds the self-contained headless render runtime (render.html + snapshot-render.js)
# into the packaged runtime (packages/cadgen/src/cadgen/_runtime/browser). Sourced by
# scripts/bundle/cadgen-runtime.sh.
#
# The snapshot CLI drives this bundle in a Playwright page. It is built from the same
# cadgen-js entrypoint the CAD Viewer uses, so the picture a snapshot produces matches the
# viewport; STEP models, meshes and drawings all render through it.
#
# Callers set SNAPSHOT_RUNTIME_BUILD_DEPS_DIR (npm scratch) before sourcing, or accept the
# default. Everything else is passed per call.

SNAPSHOT_RUNTIME_ESBUILD_VERSION="${CAD_SNAPSHOT_ESBUILD_VERSION:-0.27.7}"

# three and meshoptimizer are read from packages/cadgen-js/package-lock.json, the one
# place their exact versions are already pinned, so a dependency bump cannot silently change
# what ships without also changing the committed bundle. This matches node_builders.sh.
# Resolved lazily: BUNDLE_REPO_ROOT is set before the first call, not necessarily before
# sourcing.
snapshot_runtime_locked_version() {
  local name="$1"
  node -p "
    const lock = require('$BUNDLE_REPO_ROOT/packages/cadgen-js/package-lock.json');
    const entry = lock.packages && lock.packages['node_modules/$name'];
    if (!entry || !entry.version) {
      throw new Error('packages/cadgen-js/package-lock.json has no pinned $name');
    }
    entry.version;
  "
}

# The lockfile version, unless the matching CAD_SNAPSHOT_* env var overrides it.
snapshot_runtime_pinned_version() {
  local name="$1"
  local override
  case "$name" in
    three) override="${CAD_SNAPSHOT_THREE_VERSION:-}" ;;
    meshoptimizer) override="${CAD_SNAPSHOT_MESHOPTIMIZER_VERSION:-}" ;;
    *) override="" ;;
  esac
  if [ -n "$override" ]; then
    printf '%s\n' "$override"
    return 0
  fi
  snapshot_runtime_locked_version "$name"
}

snapshot_runtime_entrypoint() {
  printf '%s\n' "$BUNDLE_REPO_ROOT/packages/cadgen-js/src/common/headlessRenderEntry.js"
}

# snapshot_runtime_need_install <deps_dir> <three> <meshoptimizer>
snapshot_runtime_need_install() {
  local deps_dir="$1"
  local three="$2"
  local meshoptimizer="$3"
  [ -x "$deps_dir/node_modules/.bin/esbuild" ] || return 0
  node <<EOF || return 0
const deps = {
  esbuild: "$SNAPSHOT_RUNTIME_ESBUILD_VERSION",
  three: "$three",
  meshoptimizer: "$meshoptimizer",
};
for (const [name, expected] of Object.entries(deps)) {
  const actual = require("$deps_dir/node_modules/" + name + "/package.json").version;
  if (actual !== expected) {
    process.exit(1);
  }
}
EOF
  return 1
}

# ensure_snapshot_runtime_deps <deps_dir> <install_allowed>
ensure_snapshot_runtime_deps() {
  local deps_dir="$1"
  local install_allowed="${2:-1}"
  for tool in npm node; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "$tool is required to build the snapshot runtime." >&2
      exit 1
    fi
  done
  # Resolved once, and a failure here is fatal: falling through with an empty version
  # would npm-install `three@`, which resolves to latest rather than the pinned build.
  local three meshoptimizer
  three="$(snapshot_runtime_pinned_version three)" || exit 1
  meshoptimizer="$(snapshot_runtime_pinned_version meshoptimizer)" || exit 1
  if snapshot_runtime_need_install "$deps_dir" "$three" "$meshoptimizer"; then
    if [ "$install_allowed" -eq 0 ]; then
      echo "Missing or stale build dependencies in $deps_dir." >&2
      echo "Run without --no-install to install them." >&2
      exit 1
    fi
    mkdir -p "$deps_dir"
    npm install --prefix "$deps_dir" --no-audit --no-fund \
      --fetch-retries=1 --fetch-timeout=10000 \
      "esbuild@$SNAPSHOT_RUNTIME_ESBUILD_VERSION" \
      "three@$three" \
      "meshoptimizer@$meshoptimizer"
  fi
}

write_snapshot_render_html() {
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

# build_snapshot_runtime <target_dir> <deps_dir>
build_snapshot_runtime() {
  local target_dir="$1"
  local deps_dir="$2"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  write_snapshot_render_html "$target_dir"
  # NODE_PATH resolves cadgen-js's remaining bare imports directly
  # from packages/ source, honoring the package's exports map, and resolves the
  # pinned meshoptimizer out of the tmp toolchain, so the bundle stays hermetic
  # on fresh checkouts with no packages/cadgen-js/node_modules.
  # A directory --alias cannot do the first: it bypasses the exports map.
  #
  # meshoptimizer MUST be resolvable here. glbMeshData.js reaches it through a
  # dynamic import("meshoptimizer"), which esbuild leaves as a bare specifier --
  # with no error and no warning -- when it cannot resolve it. The call site
  # catches the failure and renders on without a decoder, so a bundle built
  # without it silently loses EXT_meshopt_compression support instead of failing
  # the build.
  NODE_PATH="$BUNDLE_REPO_ROOT/packages:$deps_dir/node_modules" \
    "$deps_dir/node_modules/.bin/esbuild" "$(snapshot_runtime_entrypoint)" \
    --bundle \
    --format=esm \
    --platform=browser \
    --target=es2022 \
    --main-fields=module,main \
    --minify \
    --legal-comments=none \
    --alias:three="$deps_dir/node_modules/three" \
    --outfile="$target_dir/snapshot-render.js"
}

# check_snapshot_runtime <runtime_dir> <check_dir> <repo_relative_label> <fix_hint>
check_snapshot_runtime() {
  local runtime_dir="$1"
  local check_dir="$2"
  local label="$3"
  local fix_hint="$4"
  local stale=0
  for file in render.html snapshot-render.js; do
    if [ ! -f "$runtime_dir/$file" ]; then
      echo "Missing generated runtime file: $label/$file" >&2
      stale=1
      continue
    fi
    if ! cmp -s "$check_dir/$file" "$runtime_dir/$file"; then
      echo "Stale generated runtime file: $label/$file" >&2
      stale=1
    fi
  done
  if [ "$stale" -ne 0 ]; then
    echo "" >&2
    echo "$fix_hint" >&2
    return 1
  fi
  return 0
}
