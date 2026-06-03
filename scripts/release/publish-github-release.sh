#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

REMOTE="${RELEASE_REMOTE:-origin}"
REPO=""
DRY_RUN=0
CREATE_RELEASE=1
DRAFT=1
TARGET_REF="HEAD"
SKIP_EXISTING_VERSION=0

usage() {
  cat <<'EOF'
Usage:
  scripts/release/publish-github-release.sh [options]

Creates the immutable release identity for the current repo version:

1. verifies plugins/cad/VERSION contains a valid canonical version
2. verifies a new version is greater than the latest local semver tag
3. creates and pushes the semver git tag for plugins/cad/VERSION
4. creates a GitHub Release for that tag with generated notes

Options:
  --target REF       Commit/ref to tag. Defaults to HEAD.
  --remote NAME     Git remote to push tags to. Defaults to origin.
  --repo OWNER/REPO GitHub repository for gh release commands.
  --dry-run         Print planned tag/release actions without writing.
  --skip-existing-version
                    Exit successfully when the version tag already exists.
  --skip-release    Create/push the tag but do not create a GitHub Release.
  --draft           Create a draft GitHub Release. This is the default.
  --publish         Publish the GitHub Release immediately.
  -h, --help        Show this help.

The workflow path should run this from the production branch after generated
outputs have been validated. Local use is a manual fallback.
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
    --remote)
      [ "$#" -ge 2 ] || die "--remote requires a value"
      REMOTE="$2"
      shift
      ;;
    --repo)
      [ "$#" -ge 2 ] || die "--repo requires a value"
      REPO="$2"
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-existing-version)
      SKIP_EXISTING_VERSION=1
      ;;
    --skip-release)
      CREATE_RELEASE=0
      ;;
    --draft)
      DRAFT=1
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

version="$(tr -d '[:space:]' < "$REPO_ROOT/plugins/cad/VERSION")"
[ -n "$version" ] || die "plugins/cad/VERSION is empty"
tag_name="$version"
target_commit="$(git rev-parse "$TARGET_REF^{commit}")"
latest_tag="$(git tag --list '[0-9]*.[0-9]*.[0-9]*' --sort=-version:refname | head -n 1 || true)"

tag_commit=""
if git rev-parse --verify --quiet "refs/tags/$tag_name" >/dev/null; then
  tag_commit="$(git rev-list -n 1 "$tag_name")"
fi

if [ -n "$tag_commit" ]; then
  if [ "$tag_commit" != "$target_commit" ]; then
    if [ "$SKIP_EXISTING_VERSION" -eq 1 ]; then
      echo "Release tag already exists for $tag_name at $tag_commit; skipping $target_commit."
      exit 0
    fi
    die "release tag $tag_name already points at $tag_commit, not $target_commit"
  fi
  echo "Release tag already points at target commit: $tag_name"
else
  if [ -n "$latest_tag" ]; then
    "$SCRIPT_DIR/check-version.sh" --incremented-from "refs/tags/$latest_tag"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "Would create release tag: $tag_name -> $target_commit"
    echo "Would push release tag to $REMOTE"
  else
    git tag "$tag_name" "$target_commit"
    git push "$REMOTE" "refs/tags/$tag_name"
    echo "Created and pushed release tag: $tag_name"
  fi
fi

if [ "$CREATE_RELEASE" -eq 0 ]; then
  echo "Skipping GitHub Release creation."
  exit 0
fi

gh_repo_args=()
if [ -n "$REPO" ]; then
  gh_repo_args=(-R "$REPO")
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

if gh "${gh_repo_args[@]}" release view "$tag_name" >/dev/null 2>&1; then
  echo "GitHub Release already exists: $tag_name"
  exit 0
fi

release_args=(release create "$tag_name" --verify-tag --generate-notes --title "$tag_name")
if [ "$DRAFT" -eq 1 ]; then
  release_args+=(--draft)
fi
gh "${gh_repo_args[@]}" "${release_args[@]}"
echo "Created GitHub Release: $tag_name"
