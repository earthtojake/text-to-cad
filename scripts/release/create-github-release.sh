#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

BUMP_VERSION="$SCRIPT_DIR/bump-version.sh"
REMOTE="${RELEASE_REMOTE:-origin}"
REPO=""
DRY_RUN=0
SKIP_CHECKS=0
RUN_TESTS=0
SKIP_PUSH=0
SKIP_RELEASE=0
PUBLISH=0
BUMP_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/release/create-github-release.sh <major|minor|patch> [options]
  scripts/release/create-github-release.sh --set-version X.Y.Z [options]

Runs the repo release-prep flow:

1. calls scripts/release/bump-version.sh
2. bundles generated skill/plugin outputs
3. runs generated-output and plugin checks
4. commits the release version bump
5. creates and pushes the git tag
6. creates a draft GitHub Release for that tag

Options:
  --from-version X.Y.Z  Pass through to bump-version.sh.
  --set-version X.Y.Z   Pass through to bump-version.sh instead of bumping a part.
  --dry-run             Show the planned bump and release steps without writing.
  --skip-checks         Skip bundle/check scripts after bumping.
  --run-tests           Run scripts/test/test.sh before committing.
  --skip-push           Do not push the branch or tag.
  --skip-release        Do not create the GitHub Release.
  --publish             Publish the GitHub Release immediately instead of creating a draft.
  --remote NAME         Git remote to push to. Defaults to origin.
  --repo OWNER/REPO     GitHub repository for gh release commands.
  -h, --help            Show this help.

The worktree must be clean before a non-dry-run release prep starts.
This is a manual all-in-one fallback. Prefer the Prepare Release and Publish
GitHub Actions workflows for normal releases.
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
    major|minor|patch)
      BUMP_ARGS+=("$1")
      ;;
    --from-version|--set-version|--remote|--repo)
      [ "$#" -ge 2 ] || die "$1 requires a value"
      case "$1" in
        --remote)
          REMOTE="$2"
          ;;
        --repo)
          REPO="$2"
          ;;
        *)
          BUMP_ARGS+=("$1" "$2")
          ;;
      esac
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-checks)
      SKIP_CHECKS=1
      ;;
    --run-tests)
      RUN_TESTS=1
      ;;
    --skip-push)
      SKIP_PUSH=1
      ;;
    --skip-release)
      SKIP_RELEASE=1
      ;;
    --publish)
      PUBLISH=1
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
[ -x "$BUMP_VERSION" ] || die "missing executable bump-version script: $BUMP_VERSION"

if [ "$SKIP_PUSH" -eq 1 ] && [ "$SKIP_RELEASE" -eq 0 ]; then
  die "--skip-push requires --skip-release because gh release create --verify-tag needs the remote tag"
fi

bump_output="$("$BUMP_VERSION" "${BUMP_ARGS[@]}" --dry-run)"
version_pair="$(printf '%s\n' "$bump_output" | sed -nE 's/^Version bump: ([0-9]+\.[0-9]+\.[0-9]+) -> ([0-9]+\.[0-9]+\.[0-9]+)$/\1 \2/p')"
[ -n "$version_pair" ] || die "could not determine target version from bump-version.sh"
read -r current_version next_version <<<"$version_pair"

if [ "$DRY_RUN" -eq 1 ]; then
  printf '%s\n' "$bump_output"
  echo ""
  echo "Release prep dry run for $current_version -> $next_version:"
  echo "- Bundle generated outputs with scripts/bundle/bundle.sh"
  if [ "$SKIP_CHECKS" -eq 0 ]; then
    echo "- Check generated outputs and plugin metadata with scripts/bundle/bundle.sh --check"
  fi
  if [ "$RUN_TESTS" -eq 1 ]; then
    echo "- Run scripts/test/test.sh"
  fi
  echo "- Commit canonical release version and bundled outputs as: Release $next_version"
  echo "- Create git tag: $next_version"
  if [ "$SKIP_PUSH" -eq 0 ]; then
    echo "- Push current branch and tag to $REMOTE"
  fi
  if [ "$SKIP_RELEASE" -eq 0 ]; then
    if [ "$PUBLISH" -eq 1 ]; then
      echo "- Create published GitHub Release: $next_version"
    else
      echo "- Create draft GitHub Release: $next_version"
    fi
  fi
  exit 0
fi

branch="$(git symbolic-ref -q --short HEAD || true)"
[ -n "$branch" ] || die "release prep must run on a named branch, not detached HEAD"

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  die "working tree must be clean before release prep starts"
fi

if git rev-parse -q --verify "refs/tags/$next_version" >/dev/null; then
  die "local tag already exists: $next_version"
fi

if git ls-remote --exit-code --tags "$REMOTE" "refs/tags/$next_version" >/dev/null 2>&1; then
  die "remote tag already exists on $REMOTE: $next_version"
else
  ls_remote_status=$?
  if [ "$ls_remote_status" -ne 2 ]; then
    die "failed to check remote tags on $REMOTE"
  fi
fi

if [ "$SKIP_RELEASE" -eq 0 ]; then
  require_command gh
  gh_repo_args=()
  if [ -n "$REPO" ]; then
    gh_repo_args=(-R "$REPO")
  fi
  if gh "${gh_repo_args[@]}" release view "$next_version" >/dev/null 2>&1; then
    die "GitHub Release already exists: $next_version"
  fi
fi

"$BUMP_VERSION" "${BUMP_ARGS[@]}"

"$REPO_ROOT/scripts/bundle/bundle.sh"

if [ "$SKIP_CHECKS" -eq 0 ]; then
  "$REPO_ROOT/scripts/bundle/bundle.sh" --check
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  "$REPO_ROOT/scripts/test/test.sh"
fi

git add -A
if git diff --cached --quiet; then
  die "release prep did not produce any committed changes"
fi

git commit -m "Release $next_version"
git tag "$next_version"

if [ "$SKIP_PUSH" -eq 0 ]; then
  git push "$REMOTE" "$branch"
  git push "$REMOTE" "$next_version"
fi

if [ "$SKIP_RELEASE" -eq 0 ]; then
  release_args=(release create "$next_version" --verify-tag --generate-notes --title "$next_version")
  if [ "$PUBLISH" -eq 0 ]; then
    release_args+=(--draft)
  fi
  gh "${gh_repo_args[@]}" "${release_args[@]}"
fi

echo "Prepared release $next_version."
