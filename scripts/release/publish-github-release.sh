#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=release-tags.sh
source "$SCRIPT_DIR/release-tags.sh"

DRY_RUN=0
DRAFT=1
TARGET_REF="HEAD"

usage() {
  cat <<'EOF'
Usage:
  scripts/release/publish-github-release.sh [--target REF] [--dry-run] [--publish]

Creates the immutable release identity for the current repo version:

1. verifies VERSION contains a valid canonical version
2. verifies a new version is greater than the latest local release tag
3. creates the release tag for VERSION (`v<VERSION>`) and pushes it to origin
4. creates a GitHub Release for that tag with generated notes

Options:
  --target REF  Commit/ref to tag. Defaults to HEAD.
  --dry-run     Print the planned tag/release actions without writing.
  --publish     Publish the GitHub Release immediately; the default is a draft.
  -h, --help    Show this help.

Publish Release runs this on the merged release commit after generated outputs
have been validated. Local use is a manual fallback for the same commit.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || die "--target requires a value"
      TARGET_REF="$2"
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --publish)
      DRAFT=0
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

require_command git

"$SCRIPT_DIR/check-version.sh"

version="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
[ -n "$version" ] || die "VERSION is empty"
tag_name="$(release_tag_name "$version")"
target_commit="$(git rev-parse "$TARGET_REF^{commit}")"
# Either spelling: releases before 0.5.0 were tagged bare (see release-tags.sh).
latest_tag="$(latest_release_tag)"

tag_commit=""
if git rev-parse --verify --quiet "refs/tags/$tag_name" >/dev/null; then
  tag_commit="$(git rev-list -n 1 "$tag_name")"
fi

if [ -n "$tag_commit" ]; then
  if [ "$tag_commit" != "$target_commit" ]; then
    die "release tag $tag_name already points at $tag_commit, not $target_commit"
  fi
  echo "Release tag already points at target commit: $tag_name"
else
  if [ -n "$latest_tag" ]; then
    "$SCRIPT_DIR/check-version.sh" --incremented-from "refs/tags/$latest_tag"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "Would create release tag: $tag_name -> $target_commit"
    echo "Would push release tag to origin"
  else
    git tag "$tag_name" "$target_commit"
    git push origin "refs/tags/$tag_name"
    echo "Created and pushed release tag: $tag_name"
  fi
fi

if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$DRAFT" -eq 1 ]; then
    echo "Would create draft GitHub Release: $tag_name"
  else
    echo "Would create published GitHub Release: $tag_name"
  fi
  exit 0
fi

require_command gh

if gh release view "$tag_name" >/dev/null 2>&1; then
  echo "GitHub Release already exists: $tag_name"
  exit 0
fi

release_args=(release create "$tag_name" --verify-tag --generate-notes --title "$tag_name")
if [ "$DRAFT" -eq 1 ]; then
  release_args+=(--draft)
fi
gh "${release_args[@]}"
echo "Created GitHub Release: $tag_name"
