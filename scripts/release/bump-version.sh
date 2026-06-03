#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION_PATH="plugins/cad/VERSION"
VERSION_FILE="$REPO_ROOT/$VERSION_PATH"

PART=""
SET_VERSION=""
FROM_VERSION=""
DRY_RUN=0
CHECK=0
CHECK_INCREMENTED_FROM=""
COMMIT=0
AMEND=0
NO_EDIT=0
NO_VERIFY=0
SIGNOFF=0
TAG=0
FORCE_TAG=0
MESSAGES=()

usage() {
  cat <<'EOF'
Usage:
  scripts/release/bump-version.sh major|minor|patch [options]
  scripts/release/bump-version.sh --set-version X.Y.Z [options]
  scripts/release/bump-version.sh --check
  scripts/release/bump-version.sh --check-incremented-from REF

Bumps or checks the canonical repo release version in plugins/cad/VERSION.
Duplicate package and plugin metadata is synchronized from that file by
scripts/release/sync-version.mjs during release preparation and production
bundling.

Common options:
  --dry-run          Show planned edits and git actions without changing files.
  --no-commit       Write files but do not commit. This is the default.
  --commit          Commit the bump.
  --amend           Amend the current commit instead of creating a new commit.
  -m, --message MSG Pass a commit message to git commit. May be repeated.
  --no-edit         Reuse the current commit message with --amend.
  --no-verify       Pass --no-verify to git commit.
  --signoff         Pass --signoff to git commit.
  --no-tag          Do not create a local tag. This is the default.
  --tag             Create a local tag after committing. Manual fallback only.
  --force-tag       Move an existing local release tag to HEAD.
  --from-version X  Require the current canonical version to be X.Y.Z.
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
    major)
      printf '%s.0.0\n' "$((10#$major + 1))"
      ;;
    minor)
      printf '%s.%s.0\n' "$major" "$((10#$minor + 1))"
      ;;
    patch)
      printf '%s.%s.%s\n' "$major" "$minor" "$((10#$patch + 1))"
      ;;
    *)
      die "unknown bump part: $part"
      ;;
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

git_text_at_ref() {
  local ref="$1"
  [ -n "$ref" ] || die "base ref must not be empty"
  if [[ "$ref" =~ ^0+$ ]]; then
    die "base ref must be a real commit, not an empty all-zero ref"
  fi
  git -C "$REPO_ROOT" show "$ref:$VERSION_PATH"
}

stage_paths() {
  git -C "$REPO_ROOT" add -- "$VERSION_PATH"
}

commit_version_bump() {
  local next_version="$1"
  local command=(commit)

  stage_paths
  if [ "$AMEND" -eq 1 ]; then
    command+=(--amend)
  fi
  if [ "$NO_VERIFY" -eq 1 ]; then
    command+=(--no-verify)
  fi
  if [ "$SIGNOFF" -eq 1 ]; then
    command+=(--signoff)
  fi
  if [ "$NO_EDIT" -eq 1 ]; then
    command+=(--no-edit)
  elif [ "${#MESSAGES[@]}" -gt 0 ]; then
    local message
    for message in "${MESSAGES[@]}"; do
      command+=(-m "$message")
    done
  elif [ "$AMEND" -eq 1 ]; then
    command+=(--no-edit)
  else
    command+=(-m "Bump version to $next_version")
  fi
  git -C "$REPO_ROOT" "${command[@]}"
}

tag_exists() {
  git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$1" >/dev/null
}

create_release_tag() {
  local tag_name="$1"
  local tag_commit head_commit
  if tag_exists "$tag_name"; then
    tag_commit="$(git -C "$REPO_ROOT" rev-list -n 1 "$tag_name")"
    head_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    if [ "$tag_commit" = "$head_commit" ]; then
      echo "Release tag already exists on HEAD: $tag_name"
      return
    fi
    [ "$FORCE_TAG" -eq 1 ] || die "release tag already exists on a different commit: $tag_name"
    git -C "$REPO_ROOT" tag -f "$tag_name" HEAD
    echo "Moved release tag: $tag_name"
    return
  fi
  git -C "$REPO_ROOT" tag "$tag_name" HEAD
  echo "Created release tag: $tag_name"
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
    --from-version)
      [ "$#" -ge 2 ] || die "--from-version requires a value"
      FROM_VERSION="$2"
      shift
      ;;
    --from-version=*)
      FROM_VERSION="${1#--from-version=}"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --check)
      CHECK=1
      ;;
    --check-incremented-from)
      [ "$#" -ge 2 ] || die "--check-incremented-from requires a ref"
      CHECK=1
      CHECK_INCREMENTED_FROM="$2"
      shift
      ;;
    --check-incremented-from=*)
      CHECK=1
      CHECK_INCREMENTED_FROM="${1#--check-incremented-from=}"
      ;;
    --no-commit)
      COMMIT=0
      TAG=0
      ;;
    --commit)
      COMMIT=1
      ;;
    --amend)
      AMEND=1
      ;;
    -m|--message)
      [ "$#" -ge 2 ] || die "$1 requires a value"
      MESSAGES+=("$2")
      shift
      ;;
    --message=*)
      MESSAGES+=("${1#--message=}")
      ;;
    --no-edit)
      NO_EDIT=1
      ;;
    --no-verify)
      NO_VERIFY=1
      ;;
    --signoff)
      SIGNOFF=1
      ;;
    --no-tag)
      TAG=0
      ;;
    --tag)
      TAG=1
      ;;
    --force-tag)
      FORCE_TAG=1
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

if [ "$CHECK" -eq 1 ]; then
  if [ -n "$PART" ] || [ -n "$SET_VERSION" ] || [ -n "$FROM_VERSION" ] || [ "$DRY_RUN" -eq 1 ] ||
    [ "$COMMIT" -eq 1 ] || [ "$AMEND" -eq 1 ] || [ "${#MESSAGES[@]}" -gt 0 ] ||
    [ "$NO_EDIT" -eq 1 ] || [ "$NO_VERIFY" -eq 1 ] || [ "$SIGNOFF" -eq 1 ] ||
    [ "$TAG" -eq 1 ] || [ "$FORCE_TAG" -eq 1 ]; then
    die "version bump, git commit, and tag arguments cannot be combined with check modes"
  fi

  current_version="$(read_version)"
  if [ -n "$CHECK_INCREMENTED_FROM" ]; then
    base_version="$(git_text_at_ref "$CHECK_INCREMENTED_FROM" | tr -d '[:space:]')"
    validate_semver "$base_version"
    if ! semver_greater "$current_version" "$base_version"; then
      die "current version $current_version must be greater than $base_version from $CHECK_INCREMENTED_FROM"
    fi
    echo "Canonical release version is incremented from $CHECK_INCREMENTED_FROM: $base_version -> $current_version"
  else
    echo "Canonical release version is valid: $current_version"
  fi
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
if [ -n "$FROM_VERSION" ]; then
  validate_semver "$FROM_VERSION"
fi
if [ "$COMMIT" -eq 1 ] && [ "$AMEND" -eq 1 ]; then
  die "--commit and --amend are mutually exclusive"
fi
if [ "$NO_EDIT" -eq 1 ] && [ "$AMEND" -eq 0 ]; then
  die "--no-edit only applies with --amend"
fi
if [ "$NO_EDIT" -eq 1 ] && [ "${#MESSAGES[@]}" -gt 0 ]; then
  die "--no-edit cannot be combined with --message"
fi
if [ "$TAG" -eq 1 ] && [ "$COMMIT" -eq 0 ] && [ "$AMEND" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  die "--tag requires --commit or --amend"
fi
if [ "$FORCE_TAG" -eq 1 ] && [ "$TAG" -eq 0 ]; then
  die "--force-tag requires --tag"
fi

current_version="$(read_version)"
if [ -n "$FROM_VERSION" ] && [ "$current_version" != "$FROM_VERSION" ]; then
  die "$VERSION_PATH is $current_version, expected $FROM_VERSION"
fi

if [ -n "$SET_VERSION" ]; then
  next_version="$SET_VERSION"
else
  next_version="$(bump_version "$current_version" "$PART")"
fi

if [ "$next_version" = "$current_version" ]; then
  die "next version matches current version: $current_version"
fi

echo "Version bump: $current_version -> $next_version"
echo "- $VERSION_PATH (canonical plugin version)"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run only; no files changed."
  if [ "$COMMIT" -eq 1 ] || [ "$AMEND" -eq 1 ]; then
    if [ "$AMEND" -eq 1 ]; then
      echo "Would amend the current commit."
    else
      echo "Would create a commit."
    fi
  fi
  if [ "$TAG" -eq 1 ]; then
    echo "Would create release tag: $next_version"
  fi
  echo "Release prep workflow: gh workflow run prepare-release.yml"
  echo "Local fallback: scripts/release/bump-version.sh --set-version $next_version --no-commit"
  exit 0
fi

printf '%s\n' "$next_version" > "$VERSION_FILE"
echo "Updated 1 file."

if [ "$COMMIT" -eq 1 ] || [ "$AMEND" -eq 1 ]; then
  commit_version_bump "$next_version"
  echo "Committed version bump."
fi

if [ "$TAG" -eq 1 ]; then
  create_release_tag "$next_version"
elif [ "$COMMIT" -eq 1 ] || [ "$AMEND" -eq 1 ]; then
  echo "Release tag to create separately: $next_version"
else
  echo "Release prep workflow: gh workflow run prepare-release.yml"
  echo "Local fallback: scripts/release/bump-version.sh --set-version $next_version --no-commit"
fi
