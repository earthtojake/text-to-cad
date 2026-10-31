#!/usr/bin/env bash
set -euo pipefail

# Build the server's non-Python runtime INTO ITS PACKAGE (packages/texttocad-server/src/cad_server/_runtime).
#
# The server ships three things it does not write in Python: the CAD Viewer's built client
# (`cad viewer` serves it), the one-file CAD app an agent host renders (`cad-mcp`
# serves it), and the agent-app plugin -- the repository root's plugin files and the skills --
# which it writes into the plugin folder every agent app is pointed at (`cad plugin`,
# cad_server/_internal/plugin.py). (The OCCT parity bench's headless page of the viewer's scene
# is not one of them: the engine's snapshots are OCCT's, so lib/snapshot_runtime.sh builds that
# page into tmp/ when the bench asks for it, never into the wheel.)
# The server resolves them inside its distribution, so there is one copy and one builder of
# that copy: this script. scripts/bundle/bundle.sh is the entry point that calls it (after
# stamping derived version metadata); call this directly only when debugging one stage.
#
# Stages (default: all three):
#   --viewer    CAD Viewer client (vite)               -> _runtime/viewer
#   --mcp       CAD app page (vite)                    -> _runtime/mcp
#   --plugin    the plugin's files and skills/ (copies) -> _runtime/plugin
#
# NOTHING here is committed. The whole _runtime tree is gitignored and built on demand:
# the wheel is the only place these files ship, and a rebundle of a built page is
# megabytes of churn per commit. So there is no committed copy to diff against,
# and `--check` means "the runtime BUILDS and every required output is there" rather than
# "the committed copy is fresh": it builds into _runtime like a normal run and then
# asserts the files each stage owes. scripts/release/check-wheel-contents.sh is the gate
# that proves the wheel got them.
#
# `--print-outputs` lists the directories a bundle always produces; `--print-plugin-files` the
# plugin's files the plugin stage copies beside skills/.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RUNTIME_DIR="$REPO_ROOT/packages/texttocad-server/src/cad_server/_runtime"
VIEWER_DIR="$RUNTIME_DIR/viewer"
VIEWER_APP_DIR="$REPO_ROOT/apps/web"
MCP_DIR="$RUNTIME_DIR/mcp"
MCP_APP_DIR="$REPO_ROOT/apps/mcp"
PLUGIN_DIR="$RUNTIME_DIR/plugin"
VIEWER_PACKAGE_MANAGER="${CAD_VIEWER_PACKAGE_MANAGER:-}"

# The plugin's files beside its skills: the repository root's plugin layout, as the `latest`
# branch carries it but its README (scripts/release/plugin_branch.py), and as the server writes it
# into the plugin folder (cad_server/_internal/plugin.py FILES). tests/python/global/test_plugin_folder.py
# holds the three lists equal.
PLUGIN_FILES=(
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
  .claude-plugin/icon.png
  .codex-plugin/plugin.json
  .codex-plugin/logo.png
  .cursor-plugin/plugin.json
  gemini-extension.json
  plugin.json
  mcp.json
  claude.mcp.json
  codex.mcp.json
  cursor.mcp.json
  LICENSE
)

# What each stage owes, checked after a --check build. A stage that emits nothing is the
# failure this catches before a wheel carries the hole to a user. Each page ships beside it the
# third-party notice its build wrote of the packages it inlines (THIRD_PARTY_LICENSES.txt,
# @text-to-cad/core/third-party-licenses): shipping them in a wheel is redistribution. The
# plugin owes its files and every skill, byte for byte (check_plugin_copy).
VIEWER_OUTPUTS=(index.html THIRD_PARTY_LICENSES.txt)
MCP_OUTPUTS=(shell.html app.js THIRD_PARTY_LICENSES.txt)

MODE="write"
CLEAN=0
PRINT_OUTPUTS=0
PRINT_PLUGIN_FILES=0
STAGE_VIEWER=0
STAGE_MCP=0
STAGE_PLUGIN=0
ANY_STAGE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/cadgen-runtime.sh [--check] [--clean] [--print-outputs] [stages...]

Builds the server's packaged runtime assets into packages/texttocad-server/src/cad_server/_runtime.
None of it is committed; the wheel is where it ships.

Stages (default: all three):
  --viewer    CAD Viewer client (vite)                -> _runtime/viewer
  --mcp       CAD app page (vite)                     -> _runtime/mcp
  --plugin    the plugin's files and skills/ (copies) -> _runtime/plugin

Options:
  --check               Build, then assert every required output exists.
  --clean               Remove the _runtime tree first, so the build starts from nothing.
  --print-outputs       Print the generated output paths (repo-relative), then exit.
  --print-plugin-files  Print the plugin's files the plugin stage copies beside skills/, then exit.
  -h, --help            Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --clean) CLEAN=1 ;;
    --print-outputs) PRINT_OUTPUTS=1 ;;
    --print-plugin-files) PRINT_PLUGIN_FILES=1 ;;
    --viewer) STAGE_VIEWER=1; ANY_STAGE=1 ;;
    --mcp) STAGE_MCP=1; ANY_STAGE=1 ;;
    --plugin) STAGE_PLUGIN=1; ANY_STAGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$ANY_STAGE" -eq 0 ]; then
  STAGE_VIEWER=1; STAGE_MCP=1; STAGE_PLUGIN=1
fi

if [ "$PRINT_OUTPUTS" -eq 1 ]; then
  printf '%s\n' "${VIEWER_DIR#"$REPO_ROOT"/}" "${MCP_DIR#"$REPO_ROOT"/}" "${PLUGIN_DIR#"$REPO_ROOT"/}"
  exit 0
fi

if [ "$PRINT_PLUGIN_FILES" -eq 1 ]; then
  printf '%s\n' "${PLUGIN_FILES[@]}"
  exit 0
fi

# --clean builds from nothing rather than over whatever is there. Each stage already
# clears its own directory, so this only matters when a stage or a file has been RENAMED
# and the old one would otherwise survive to be packaged.
if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$RUNTIME_DIR"
fi

# What _runtime holds is what this script builds and nothing else: an entry no stage owns (one a
# stage this script no longer has left behind) would otherwise ship in the next wheel, since
# package-data takes the whole tree. It goes whatever stages this run builds.
STAGE_DIRS=(viewer mcp plugin)
prune_stale_runtime() {
  local entry name stage known
  [ -d "$RUNTIME_DIR" ] || return 0
  for entry in "$RUNTIME_DIR"/* "$RUNTIME_DIR"/.[!.]*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    name="${entry##*/}"
    known=0
    for stage in "${STAGE_DIRS[@]}"; do [ "$name" = "$stage" ] && known=1; done
    if [ "$known" -eq 0 ]; then
      rm -rf "$entry"
      echo "Removed packages/texttocad-server/src/cad_server/_runtime/$name: no stage builds it."
    fi
  done
}
prune_stale_runtime

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

# --- the CAD app an agent host renders ------------------------------------------------
# The shell a host keeps (shell.html, small and self-contained) and the app it loads from
# the engine (app.js, one module: its vite build inlines scripts, styles, workers and
# fonts), so the stage owes those files and the notice beside them.
build_mcp_app() {
  local target="$1" package_manager
  require_command node
  [ -f "$MCP_APP_DIR/package.json" ] || { echo "Missing CAD app: $MCP_APP_DIR" >&2; exit 1; }
  package_manager="$(resolve_viewer_package_manager)"
  require_command "$package_manager"
  case "$package_manager" in
    pnpm) CI=true pnpm --dir "$MCP_APP_DIR" run build ;;
    npm)  npm --prefix "$MCP_APP_DIR" run build ;;
    *)
      echo "Unsupported package manager: $package_manager" >&2
      exit 1
      ;;
  esac
  for built in shell.html app.js; do
    if [ ! -f "$MCP_APP_DIR/dist/$built" ]; then
      echo "Missing CAD app build: $MCP_APP_DIR/dist/$built" >&2
      exit 1
    fi
  done
  rm -rf "$target"
  mkdir -p "$target"
  cp "$MCP_APP_DIR/dist/shell.html" "$target/shell.html"
  cp "$MCP_APP_DIR/dist/app.js" "$target/app.js"
  cp "$MCP_APP_DIR/dist/THIRD_PARTY_LICENSES.txt" "$target/THIRD_PARTY_LICENSES.txt"
}

# --- the agent-app plugin ----------------------------------------------------------------
# The repository root's plugin files and the skills, copied as they are: the server writes the
# plugin folder every agent app is pointed at from them (cad_server/_internal/plugin.py), so its
# wheel carries them. A skill's files are those git keeps (tracked, or new and not ignored), never
# a checkout's ignored ones (a __pycache__), each a real file: no installer gets a symlink
# (check-builds.sh), and Codex would drop one.
plugin_skill_files() {
  local relative
  if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$REPO_ROOT" ls-files --cached --others --exclude-standard -- skills | LC_ALL=C sort -u |
      while IFS= read -r relative; do
        if [ -f "$REPO_ROOT/$relative" ]; then printf '%s\n' "$relative"; fi
      done
  else
    (cd "$REPO_ROOT" && find skills -type f ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.*' | LC_ALL=C sort)
  fi
}

build_plugin() {
  local target="$1" relative
  rm -rf "$target"
  mkdir -p "$target"
  for relative in "${PLUGIN_FILES[@]}"; do
    [ -f "$REPO_ROOT/$relative" ] || { echo "Missing plugin file: $relative" >&2; exit 1; }
    mkdir -p "$target/$(dirname "$relative")"
    cp -p "$REPO_ROOT/$relative" "$target/$relative"
  done
  while IFS= read -r relative; do
    mkdir -p "$target/$(dirname "$relative")"
    cp -p "$REPO_ROOT/$relative" "$target/$relative"
  done < <(plugin_skill_files)
}

# The plugin stage owes exactly the plugin's files and every skill file, byte for byte.
check_plugin_copy() {
  local expected copied relative gaps=0
  expected="$({ printf '%s\n' "${PLUGIN_FILES[@]}"; plugin_skill_files; } | LC_ALL=C sort)"
  copied="$(cd "$PLUGIN_DIR" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)"
  if [ "$expected" != "$copied" ]; then
    echo "packages/texttocad-server/src/cad_server/_runtime/plugin does not hold exactly the plugin's files and skills:" >&2
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$copied") >&2 || true
    gaps=1
  else
    while IFS= read -r relative; do
      if ! cmp -s "$REPO_ROOT/$relative" "$PLUGIN_DIR/$relative"; then
        echo "packages/texttocad-server/src/cad_server/_runtime/plugin/$relative differs from $relative" >&2
        gaps=1
      fi
    done <<< "$expected"
  fi
  if [ "$gaps" -ne 0 ]; then
    missing=1
  else
    echo "packages/texttocad-server/src/cad_server/_runtime/plugin built ($(printf '%s\n' "$expected" | wc -l | tr -d ' ') files, each as the checkout holds it)."
  fi
}

build_stage_packages() {
  # Both page stages bundle @text-to-cad/core and @text-to-cad/ui from their compiled exports.
  npm --prefix "$REPO_ROOT" run build:packages
}

build_all() {
  local root="$1"
  if [ "$STAGE_VIEWER" -eq 1 ]; then
    build_viewer_client "$root/viewer"
    echo "Bundled ${root#"$REPO_ROOT"/}/viewer"
  fi
  if [ "$STAGE_MCP" -eq 1 ]; then
    build_mcp_app "$root/mcp"
    echo "Bundled ${root#"$REPO_ROOT"/}/mcp"
  fi
  if [ "$STAGE_PLUGIN" -eq 1 ]; then
    build_plugin "$root/plugin"
    echo "Bundled ${root#"$REPO_ROOT"/}/plugin"
  fi
}

mkdir -p "$RUNTIME_DIR"
if [ "$STAGE_VIEWER" -eq 1 ] || [ "$STAGE_MCP" -eq 1 ]; then
  build_stage_packages
fi
build_all "$RUNTIME_DIR"

if [ "$MODE" = "check" ]; then
  missing=0
  check_stage_outputs() {
    local stage="$1"
    shift
    local name gaps=0
    for name in "$@"; do
      if [ ! -f "$RUNTIME_DIR/$stage/$name" ]; then
        echo "Missing runtime output: packages/texttocad-server/src/cad_server/_runtime/$stage/$name" >&2
        gaps=1
        missing=1
      fi
    done
    if [ "$gaps" -eq 0 ]; then
      echo "packages/texttocad-server/src/cad_server/_runtime/$stage built ($# files)."
    fi
  }
  if [ "$STAGE_VIEWER" -eq 1 ]; then
    check_stage_outputs viewer "${VIEWER_OUTPUTS[@]}"
  fi
  if [ "$STAGE_MCP" -eq 1 ]; then
    check_stage_outputs mcp "${MCP_OUTPUTS[@]}"
  fi
  if [ "$STAGE_PLUGIN" -eq 1 ]; then
    check_plugin_copy
  fi
  if [ "$missing" -ne 0 ]; then
    echo "" >&2
    echo "The bundler ran but did not produce everything the server needs. This is a bundler" >&2
    echo "or dependency failure, not a stale checkout: rerun scripts/bundle/bundle.sh --clean" >&2
    echo "and read the build output above." >&2
    exit 1
  fi
  echo "The server's packaged runtime builds and is complete."
fi
