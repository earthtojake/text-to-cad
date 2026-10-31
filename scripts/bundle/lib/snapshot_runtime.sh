#!/usr/bin/env bash
# Builds the headless snapshot page of the viewer's scene (render.html + snapshot-render.js)
# into a directory under the repository's ignored tmp/, on demand:
#
#   scripts/bundle/lib/snapshot_runtime.sh [OUT_DIR]   (default: tmp/bench/snapshot-page)
#
# Nothing cadgen ships loads it -- cadgen's snapshots are drawn by OCCT, and the wheel does
# not carry this page. Its one reader is the OCCT parity bench (scripts/bench/occt_parity.py),
# which runs this before it drives the page in a headless Chromium to compare OCCT's stills
# with the viewer's: it is built from the same @text-to-cad/core entrypoint the CAD Viewer
# uses, so its picture is the viewport's.
#
# The esbuild toolchain and the pinned three/meshoptimizer are npm-installed once into
# tmp/cadgen-snapshot-build (CAD_SNAPSHOT_BUILD_DEPS_DIR names another).

SNAPSHOT_RUNTIME_ESBUILD_VERSION="${CAD_SNAPSHOT_ESBUILD_VERSION:-0.27.7}"

# three and meshoptimizer are read from package-lock.json, the one
# place their exact versions are already pinned, so a dependency bump cannot silently change
# what ships without also changing the lockfile.
snapshot_runtime_locked_version() {
  local name="$1"
  # The lockfile path travels as an ARGUMENT, not inside the script text: on
  # Windows, Git Bash rewrites POSIX-style paths in arguments to native ones
  # (`/d/a/x` -> `D:/a/x`), but not inside a quoted string, and Node cannot
  # open `/d/a/x`.
  node -p "
    const lock = require(process.argv[1]);
    const entry = lock.packages && lock.packages['node_modules/$name'];
    if (!entry || !entry.version) {
      throw new Error('package-lock.json has no pinned $name');
    }
    entry.version;
  " "$BUNDLE_REPO_ROOT/package-lock.json"
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
  printf '%s\n' "$BUNDLE_REPO_ROOT/packages/core/dist/common/headlessRenderEntry.js"
}

# snapshot_runtime_need_install <deps_dir> <three> <meshoptimizer>
snapshot_runtime_need_install() {
  local deps_dir="$1"
  local three="$2"
  local meshoptimizer="$3"
  [ -x "$deps_dir/node_modules/.bin/esbuild" ] || return 0
  # Pass the directory as an argument so Git Bash translates it for Node on
  # Windows; embedding `/d/a/...` in JavaScript leaves Node unable to open it.
  node -e '
const deps = {
  esbuild: process.argv[2],
  three: process.argv[3],
  meshoptimizer: process.argv[4],
};
for (const [name, expected] of Object.entries(deps)) {
  const actual = require(process.argv[1] + "/node_modules/" + name + "/package.json").version;
  if (actual !== expected) {
    process.exit(1);
  }
}
' "$deps_dir" "$SNAPSHOT_RUNTIME_ESBUILD_VERSION" "$three" "$meshoptimizer" || return 0
  return 1
}

# ensure_snapshot_runtime_deps <deps_dir>
ensure_snapshot_runtime_deps() {
  local deps_dir="$1"
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
  # NODE_PATH resolves @text-to-cad/core's remaining bare imports directly
  # from workspace outputs, honoring the package's exports map, and resolves the
  # pinned meshoptimizer out of the tmp toolchain, so the bundle stays hermetic
  # on fresh checkouts with no packages/core/node_modules.
  # A directory --alias cannot do the first: it bypasses the exports map.
  #
  # meshoptimizer MUST be resolvable here. glbMeshData.js reaches it through a
  # dynamic import("meshoptimizer"), which esbuild leaves as a bare specifier --
  # with no error and no warning -- when it cannot resolve it. The call site
  # catches the failure and renders on without a decoder, so a bundle built
  # without it silently loses EXT_meshopt_compression support instead of failing
  # the build.
  NODE_PATH="$BUNDLE_REPO_ROOT/node_modules:$deps_dir/node_modules" \
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

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  BUNDLE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  out_dir="${1:-$BUNDLE_REPO_ROOT/tmp/bench/snapshot-page}"
  deps_dir="${CAD_SNAPSHOT_BUILD_DEPS_DIR:-$BUNDLE_REPO_ROOT/tmp/cadgen-snapshot-build}"
  npm --prefix "$BUNDLE_REPO_ROOT" run build -w @text-to-cad/core >/dev/null
  ensure_snapshot_runtime_deps "$deps_dir"
  build_snapshot_runtime "$out_dir" "$deps_dir"
  echo "Built the snapshot page in $out_dir"
fi
