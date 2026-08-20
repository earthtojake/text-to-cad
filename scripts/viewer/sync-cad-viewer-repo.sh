#!/usr/bin/env bash
set -euo pipefail

# Mirror viewer/ into the standalone cad-viewer repo.
#
# This is a STRAIGHT COPY: nothing rewrites paths, commands, or prose on the way
# out. viewer/ is kept self-contained in this repo instead (enforced by
# viewer/scripts/selfContained.test.mjs), so the mirror needs no transform step
# that can silently rot between releases.
#
# The one structural change is dereferencing: viewer/packages/* is a development
# symlink layout here and must land as real directories in the mirror. Agent
# installers disagree about symlinks (see AGENTS.md), and a published tree must
# never contain one, so the copy is verified symlink-free before it is reported
# as good.
#
# Run this against a SOURCE ref (develop or a release source commit), never main:
# the publish tree drops viewer/ entirely, because it is source and what installs
# is the bundled runtime under skills/cad-viewer. What lands in packages/ is
# whatever viewer/packages/ holds -- normally the development symlinks, which
# dereference to the live package sources.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO_ROOT="$(git -C "$SCRIPT_DIR/../.." rev-parse --show-toplevel)"
SOURCE_REPO_ROOT="$(cd "$SOURCE_REPO_ROOT" && pwd -P)"
DEFAULT_TARGET="../cad-viewer"
TARGET_ARG="$DEFAULT_TARGET"
TARGET_SET=0
DRY_RUN=0
MODE="write"

# Packages that must be present under viewer/packages for the mirror to install.
# cadjs declares "implicitjs": "file:../implicitjs", so implicitjs has to ship
# alongside it or `npm install` fails in the mirror.
REQUIRED_PACKAGES=(cadjs implicitjs cadgen)

usage() {
  cat <<'EOF'
Usage:
  scripts/viewer/sync-cad-viewer-repo.sh [--check|--dry-run] [target-dir]

Copies viewer/ into a standalone cad-viewer git checkout, dereferencing the
viewer/packages/* development symlinks into real vendored copies.

Run it from a source checkout (develop or a release source commit). main is the
publish branch and carries no viewer/ at all, so it cannot be a sync source.

Default target:
  ../cad-viewer   (relative paths resolve against this repo's root)

The target must already exist and be the root of its own git repo. Everything in
the target root except .git is replaced.

Options:
  --check     Compare the target against a freshly built copy and fail if it is
              stale. Writes nothing.
  --dry-run   Print the copy plan without changing files.
  -h, --help  Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      if [ "$#" -gt 0 ]; then
        TARGET_ARG="$1"
        TARGET_SET=1
        shift
      fi
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ "$TARGET_SET" -eq 1 ]; then
        echo "Target path was provided more than once." >&2
        usage >&2
        exit 2
      fi
      TARGET_ARG="$1"
      TARGET_SET=1
      ;;
  esac
  shift
done

if [ "$#" -gt 0 ]; then
  echo "Unexpected extra arguments: $*" >&2
  usage >&2
  exit 2
fi

if [ -z "$TARGET_ARG" ]; then
  echo "Target path must not be empty." >&2
  exit 2
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required." >&2
    exit 1
  fi
}

require_path() {
  if [ ! -e "$1" ]; then
    echo "Missing $2: $1" >&2
    exit 1
  fi
}

require_command git
require_command rsync
require_command diff

VIEWER_DIR="$SOURCE_REPO_ROOT/viewer"
if [ ! -e "$VIEWER_DIR/package.json" ]; then
  echo "No viewer/ in this checkout: $VIEWER_DIR" >&2
  echo "main is the publish branch and drops viewer/ from the published tree." >&2
  echo "Sync from a source ref instead (develop, or a release source commit)." >&2
  exit 1
fi
for package_name in "${REQUIRED_PACKAGES[@]}"; do
  require_path "$VIEWER_DIR/packages/$package_name" "viewer/packages/$package_name"
done

case "$TARGET_ARG" in
  /*) TARGET_INPUT="$TARGET_ARG" ;;
  *) TARGET_INPUT="$SOURCE_REPO_ROOT/$TARGET_ARG" ;;
esac

if [ ! -d "$TARGET_INPUT" ]; then
  echo "Target directory does not exist: $TARGET_INPUT" >&2
  echo "Clone the standalone cad-viewer repo there first." >&2
  exit 1
fi

TARGET_DIR="$(cd "$TARGET_INPUT" && pwd -P)"
TARGET_GIT_ROOT="$(git -C "$TARGET_DIR" rev-parse --show-toplevel 2>/dev/null || true)"

if [ -z "$TARGET_GIT_ROOT" ]; then
  echo "Target is not inside a git repository: $TARGET_DIR" >&2
  exit 1
fi

TARGET_GIT_ROOT="$(cd "$TARGET_GIT_ROOT" && pwd -P)"

if [ "$TARGET_GIT_ROOT" != "$TARGET_DIR" ]; then
  echo "Target must be the root of its own git repo." >&2
  echo "Target:   $TARGET_DIR" >&2
  echo "Git root: $TARGET_GIT_ROOT" >&2
  exit 1
fi

if [ "$TARGET_DIR" = "$SOURCE_REPO_ROOT" ] || [ "$TARGET_DIR" = "$VIEWER_DIR" ]; then
  echo "Refusing to overwrite the source repo: $TARGET_DIR" >&2
  exit 1
fi

case "$TARGET_DIR/" in
  "$SOURCE_REPO_ROOT"/*)
    echo "Refusing to write inside the source repo: $TARGET_DIR" >&2
    exit 1
    ;;
esac

# Includes must precede the matching excludes: rsync takes the first rule that
# matches, so `--exclude '.env.*'` first would swallow `.env.example`.
RSYNC_RULES=(
  --include '.env.example'
  --include '.env.*.example'
  --exclude node_modules
  --exclude dist
  --exclude dist-verify
  --exclude .vite
  --exclude .vercel
  --exclude .next
  --exclude .next-build
  --exclude .next-dev
  --exclude .next-verify
  --exclude coverage
  --exclude tmp
  --exclude .venv
  --exclude .pytest_cache
  --exclude __pycache__
  --exclude '*.pyc'
  --exclude '*.pyo'
  --exclude '*.egg-info'
  --exclude .DS_Store
  --exclude '.env'
  --exclude '.env.*'
)

# --check runs against a target that may already have been installed and built,
# so the comparison has to ignore the same generated paths the copy skips.
DIFF_EXCLUDES=(
  -x .git
  -x node_modules
  -x dist
  -x dist-verify
  -x .vite
  -x .vercel
  -x coverage
  -x tmp
  -x .venv
  -x .pytest_cache
  -x __pycache__
  -x '*.pyc'
  -x '*.pyo'
  -x '*.egg-info'
  -x .DS_Store
  -x '.env'
)

# One pass over viewer/, including packages/. --copy-links is what turns the
# development symlinks into real directories; the mirror must never contain a
# symlink.
build_copy() {
  local destination="$1"
  mkdir -p "$destination"
  rsync -a --copy-links "${RSYNC_RULES[@]}" "$VIEWER_DIR/" "$destination/"
}

# The symlink layout is the expected one. Real directories mean bundle.sh has run
# in this checkout, so viewer/packages holds the bundle output instead of the live
# sources -- a smaller tree (cadjs ships without its own tests), which would show
# up as drift against a mirror synced normally. Say so rather than letting it look
# like real drift.
warn_on_bundled_layout() {
  local package_name
  for package_name in "${REQUIRED_PACKAGES[@]}"; do
    if [ ! -L "$VIEWER_DIR/packages/$package_name" ]; then
      echo "Note: viewer/packages holds real directories, so bundle.sh has run here and"
      echo "      this copies the bundle output rather than the live package sources."
      echo "      Run scripts/dev/setup-symlinks.sh to restore the development layout."
      return
    fi
  done
}

assert_no_symlinks() {
  local root="$1"
  local found
  found="$(find "$root" -path "$root/.git" -prune -o -type l -print)"
  if [ -n "$found" ]; then
    echo "Refusing to publish a tree containing symlinks:" >&2
    printf '%s\n' "$found" >&2
    exit 1
  fi
}

echo "Source: $VIEWER_DIR"
echo "Target: $TARGET_DIR"
warn_on_bundled_layout

if [ "$DRY_RUN" -eq 1 ]; then
  echo ""
  echo "Dry run only. Target entries that would be replaced:"
  find "$TARGET_DIR" -mindepth 1 -maxdepth 1 ! -name .git -print | sort
  echo ""
  echo "Dry run only. Copy plan:"
  echo "  $VIEWER_DIR/ -> $TARGET_DIR/   (symlinks dereferenced)"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  EXPECTED_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cad-viewer-sync-check.XXXXXX")"
  trap 'rm -rf "$EXPECTED_DIR"' EXIT
  build_copy "$EXPECTED_DIR"
  assert_no_symlinks "$EXPECTED_DIR"
  if ! diff -qr "${DIFF_EXCLUDES[@]}" "$EXPECTED_DIR" "$TARGET_DIR"; then
    echo "" >&2
    echo "The cad-viewer mirror is stale." >&2
    echo "Run scripts/viewer/sync-cad-viewer-repo.sh and commit the target repo." >&2
    exit 1
  fi
  echo "The cad-viewer mirror is up to date."
  exit 0
fi

find "$TARGET_DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
build_copy "$TARGET_DIR"
assert_no_symlinks "$TARGET_DIR"

echo ""
echo "Synced standalone CAD Viewer checkout:"
echo "  $TARGET_DIR"
echo ""
echo "Verify before publishing:"
echo "  cd \"$TARGET_DIR\""
echo "  npm install"
echo "  npm run test"
echo "  npm run build"
