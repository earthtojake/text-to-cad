#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION_PATH="VERSION"
VERSION_FILE="$REPO_ROOT/$VERSION_PATH"
# shellcheck source=release-tags.sh
source "$SCRIPT_DIR/release-tags.sh"

TARGET=""
BASE="origin/main"
DRY_RUN=0
CHECK_INCREMENTED_FROM=""

usage() {
  cat <<'EOF'
Usage:
  scripts/release/bump-version.sh major|minor|patch|X.Y.Z [--base REF] [--dry-run]
  scripts/release/bump-version.sh --check-incremented-from REF

Makes this branch a release. Sets VERSION to the next major, minor or patch
version after the one on BASE (or to X.Y.Z, which must be greater), then stamps
the derived metadata and every cadgen pin from it (sync-version.mjs: package,
plugin and lockfile versions, the plugin server configs, each skill's launch
command). The pull request that carries the change releases that version when
it merges: Publish Release runs on the merge.

The bump is relative to BASE, not to this branch, so running it again after
BASE moves (another pull request released first) moves the bump with it, and
running it twice changes nothing. BASE must already be merged into this branch,
or the stamps would conflict with BASE's.

Options:
  --base REF                   The branch this release merges into (default
                               origin/main, fetched first).
  --dry-run                    Show the planned version without changing files.
  --check-incremented-from REF Exit non-zero unless VERSION is greater than the
                               version recorded at git ref REF.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

validate_semver() {
  local version="$1"
  if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    die "expected a plain semver version like 1.2.3, got '$version'"
  fi
}

read_version() {
  local version
  [ -f "$VERSION_FILE" ] || die "missing canonical version file: $VERSION_PATH"
  version="$(tr -d '[:space:]' < "$VERSION_FILE")"
  validate_semver "$version"
  printf '%s\n' "$version"
}

bump_version() {
  local current="$1"
  local part="$2"
  local major minor patch
  validate_semver "$current"
  IFS=. read -r major minor patch <<< "$current"
  case "$part" in
    major) printf '%s.0.0\n' "$((10#$major + 1))" ;;
    minor) printf '%s.%s.0\n' "$major" "$((10#$minor + 1))" ;;
    patch) printf '%s.%s.%s\n' "$major" "$minor" "$((10#$patch + 1))" ;;
    *) die "unknown bump part: $part" ;;
  esac
}

version_at_ref() {
  local ref="$1"
  [ -n "$ref" ] || die "base ref must not be empty"
  if [[ "$ref" =~ ^0+$ ]]; then
    die "base ref must be a real commit, not an empty all-zero ref"
  fi
  git -C "$REPO_ROOT" cat-file -e "$ref:$VERSION_PATH" 2>/dev/null ||
    die "no $VERSION_PATH at $ref"
  git -C "$REPO_ROOT" show "$ref:$VERSION_PATH" | tr -d '[:space:]'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base)
      [ "$#" -ge 2 ] || die "--base requires a ref"
      BASE="$2"
      shift
      ;;
    --base=*)
      BASE="${1#--base=}"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --check-incremented-from)
      [ "$#" -ge 2 ] || die "--check-incremented-from requires a ref"
      CHECK_INCREMENTED_FROM="$2"
      shift
      ;;
    --check-incremented-from=*)
      CHECK_INCREMENTED_FROM="${1#--check-incremented-from=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      die "unknown argument: $1"
      ;;
    *)
      [ -z "$TARGET" ] || die "provide one of major, minor, patch or X.Y.Z"
      TARGET="$1"
      ;;
  esac
  shift
done

cd "$REPO_ROOT"

if [ -n "$CHECK_INCREMENTED_FROM" ]; then
  if [ -n "$TARGET" ] || [ "$DRY_RUN" -eq 1 ]; then
    die "--check-incremented-from cannot be combined with a bump"
  fi
  current_version="$(read_version)"
  base_version="$(version_at_ref "$CHECK_INCREMENTED_FROM")"
  validate_semver "$base_version"
  if ! version_greater "$current_version" "$base_version"; then
    die "current version $current_version must be greater than $base_version from $CHECK_INCREMENTED_FROM"
  fi
  echo "Canonical release version is incremented from $CHECK_INCREMENTED_FROM: $base_version -> $current_version"
  exit 0
fi

[ -n "$TARGET" ] || die "provide one of major, minor, patch or X.Y.Z"

# The base as it is now: a release that landed since the last fetch is what this one follows.
case "$BASE" in
  origin/*)
    git fetch --quiet origin "${BASE#origin/}" ||
      echo "warning: could not fetch $BASE; bumping from the copy already here." >&2
    ;;
esac
git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || die "no such base: $BASE"
if ! git merge-base --is-ancestor "$BASE" HEAD; then
  die "this branch does not contain $BASE. Merge it first (git merge $BASE), then bump: the stamps would otherwise conflict with $BASE's."
fi

base_version="$(version_at_ref "$BASE")"
case "$TARGET" in
  major|minor|patch) next_version="$(bump_version "$base_version" "$TARGET")" ;;
  *)
    validate_semver "$TARGET"
    version_greater "$TARGET" "$base_version" ||
      die "$TARGET is not greater than $base_version, the version on $BASE"
    next_version="$TARGET"
    ;;
esac

echo "Release: $base_version ($BASE) -> $next_version"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run only; no files changed."
  exit 0
fi

printf '%s\n' "$next_version" > "$VERSION_FILE"
node "$SCRIPT_DIR/sync-version.mjs"
echo "This branch releases $next_version when its pull request merges."
