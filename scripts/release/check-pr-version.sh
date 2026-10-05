#!/usr/bin/env bash
set -euo pipefail

# A pull request is a release when it changes VERSION: Publish Release runs on its merge.
# This decides whether one is, and whether it may be. Pins and derived metadata are
# check-version.sh's and sync-version.mjs --check's job; this is about the bump itself.
#
# Usage: scripts/release/check-pr-version.sh HEAD_REPO
#
#   HEAD_REPO  owner/name of the repository the pull request's branch lives in.
#
# Run it in a checkout of the pull request's merge commit, which is what actions/checkout
# checks out for a pull request. That commit's first parent is the target branch as it is
# now, so a release the branch merely inherited from the target is not taken for one it
# makes. GITHUB_REPOSITORY names this repository; the release tags must be fetched.
#
# A release writes `version=<X>` to GITHUB_OUTPUT, so the next step can hold the merge until
# that version is on PyPI. PR_NUMBER and BASE_REF, when set, name the command that releases it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-tags.sh
source "$SCRIPT_DIR/release-tags.sh"

head_repo="${1:?Usage: check-pr-version.sh HEAD_REPO}"
repository="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must name this repository}"

git rev-parse --verify --quiet "HEAD^2" >/dev/null || {
  echo "HEAD is not a merge commit; run this on the pull request's merge commit." >&2
  exit 2
}
base="$(git rev-parse "HEAD^1")"

if git diff --quiet "$base" HEAD -- VERSION; then
  echo "VERSION unchanged: merging this pull request releases nothing."
  exit 0
fi

version="$(git show "HEAD:VERSION" | tr -d '[:space:]')"
base_version="$(git show "$base:VERSION" | tr -d '[:space:]')"

# Only a branch of this repository can release: anyone can open a pull request from a fork,
# and a version bump buried in one would ship on an ordinary merge.
if [ "$head_repo" != "$repository" ]; then
  echo "This pull request changes VERSION from a fork ($head_repo)." >&2
  echo "Releases come from branches of $repository; leave VERSION alone here." >&2
  exit 1
fi

for value in "$version" "$base_version"; do
  if [[ ! "$value" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    echo "VERSION must be a plain X.Y.Z version, got '$value'." >&2
    exit 1
  fi
done

if ! version_greater "$version" "$base_version"; then
  echo "VERSION $version is not past $base_version, the version on the target branch." >&2
  echo "If another pull request released first, merge the target branch into this one and" >&2
  echo "bump again: scripts/release/bump-version.sh <major|minor|patch>." >&2
  exit 1
fi

latest_tag="$(latest_release_tag)"
if [ -n "$latest_tag" ] && ! version_greater "$version" "$(version_from_release_tag "$latest_tag")"; then
  echo "VERSION $version is not past the latest release, $latest_tag." >&2
  exit 1
fi

echo "This pull request releases $version (the target branch is at $base_version)."
echo "Release it with: gh workflow run release-publish.yml --ref ${BASE_REF:-main} -f pr=${PR_NUMBER:-<number>}"
echo "That uploads the wheel to PyPI, then merges this pull request."
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "version=$version" >> "$GITHUB_OUTPUT"
fi
