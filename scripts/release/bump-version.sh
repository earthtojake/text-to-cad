#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION_PATH="VERSION"
VERSION_FILE="$REPO_ROOT/$VERSION_PATH"
# shellcheck source=release-tags.sh
source "$SCRIPT_DIR/release-tags.sh"

PART=""
SET_VERSION=""
DRY_RUN=0
CHECK_INCREMENTED_FROM=""

usage() {
  cat <<'EOF'
Usage:
  scripts/release/bump-version.sh major|minor|patch [--dry-run]
  scripts/release/bump-version.sh --set-version X.Y.Z [--dry-run]
  scripts/release/bump-version.sh --check-incremented-from REF

Writes the canonical release version to VERSION. Nothing else: the release PR
commits it, scripts/release/sync-version.mjs stamps the derived metadata and
scripts/release/pin-cadgen-requirements.sh the skill pins, and Publish Release
tags the merge. Prepare Release is the normal caller; running it by hand is the
local fallback for that same PR.

Options:
  --dry-run                    Show the planned edit without changing the file.
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

semver_greater() {
  local left="$1"
  local right="$2"
  local left_major left_minor left_patch right_major right_minor right_patch
  validate_semver "$left"
  validate_semver "$right"
  IFS=. read -r left_major left_minor left_patch <<< "$left"
  IFS=. read -r right_major right_minor right_patch <<< "$right"

  if [ "$((10#$left_major))" -ne "$((10#$right_major))" ]; then
    [ "$((10#$left_major))" -gt "$((10#$right_major))" ]
    return
  fi
  if [ "$((10#$left_minor))" -ne "$((10#$right_minor))" ]; then
    [ "$((10#$left_minor))" -gt "$((10#$right_minor))" ]
    return
  fi
  [ "$((10#$left_patch))" -gt "$((10#$right_patch))" ]
}

version_at_ref() {
  local ref="$1"
  [ -n "$ref" ] || die "base ref must not be empty"
  if [[ "$ref" =~ ^0+$ ]]; then
    die "base ref must be a real commit, not an empty all-zero ref"
  fi
  git -C "$REPO_ROOT" cat-file -e "$ref:$VERSION_PATH" 2>/dev/null ||
    die "no $VERSION_PATH at $ref"
  git -C "$REPO_ROOT" show "$ref:$VERSION_PATH"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    major|minor|patch)
      [ -z "$PART" ] || die "provide only one semver bump part"
      PART="$1"
      ;;
    --set-version)
      [ "$#" -ge 2 ] || die "--set-version requires a value"
      SET_VERSION="$2"
      shift
      ;;
    --set-version=*)
      SET_VERSION="${1#--set-version=}"
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
    *)
      die "unknown argument: $1"
      ;;
  esac
  shift
done

cd "$REPO_ROOT"

if [ -n "$CHECK_INCREMENTED_FROM" ]; then
  if [ -n "$PART" ] || [ -n "$SET_VERSION" ] || [ "$DRY_RUN" -eq 1 ]; then
    die "--check-incremented-from cannot be combined with a bump"
  fi
  current_version="$(read_version)"
  base_version="$(version_at_ref "$CHECK_INCREMENTED_FROM" | tr -d '[:space:]')"
  validate_semver "$base_version"
  if ! semver_greater "$current_version" "$base_version"; then
    die "current version $current_version must be greater than $base_version from $CHECK_INCREMENTED_FROM"
  fi
  echo "Canonical release version is incremented from $CHECK_INCREMENTED_FROM: $base_version -> $current_version"
  exit 0
fi

if [ -n "$PART" ] && [ -n "$SET_VERSION" ]; then
  die "provide exactly one of major/minor/patch or --set-version"
fi
if [ -z "$PART" ] && [ -z "$SET_VERSION" ]; then
  die "provide exactly one of major/minor/patch or --set-version"
fi
if [ -n "$SET_VERSION" ]; then
  validate_semver "$SET_VERSION"
fi

current_version="$(read_version)"
if [ -n "$SET_VERSION" ]; then
  next_version="$SET_VERSION"
else
  next_version="$(bump_version "$current_version" "$PART")"
fi

if [ "$next_version" = "$current_version" ]; then
  # Naming the version you are already on is a pin, not a mistake: it is how a
  # caller says "leave this alone" without having to know what the version is.
  # Resolving a major/minor/patch bump to no change IS a mistake -- that one
  # still fails.
  if [ -z "$SET_VERSION" ]; then
    die "next version matches current version: $current_version"
  fi
  echo "Requested version matches current version: $current_version; nothing to change."
  exit 0
fi

echo "Version bump: $current_version -> $next_version"
echo "- $VERSION_PATH (canonical release version)"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run only; no files changed."
  echo "Release workflow: gh workflow run release-prepare.yml --ref main -f bump=<patch|minor|major>"
  exit 0
fi

printf '%s\n' "$next_version" > "$VERSION_FILE"
echo "Updated $VERSION_PATH."
echo "Release workflow: gh workflow run release-prepare.yml --ref main -f bump=<patch|minor|major>"
