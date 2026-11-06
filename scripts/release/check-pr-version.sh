#!/usr/bin/env bash
set -euo pipefail

# A pull request is a release when it changes VERSION: merging it starts Publish Release,
# which uploads the wheel to PyPI and only then moves the `latest` branch installers follow.
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

# A release that breaks nothing installs itself on every device with automatic updates on, under agent
# threads that are running, with no click: as Semantic Versioning numbers releases, one that keeps the
# breaking part -- a patch below 1.0, a patch or minor from 1.0 (version_installs_itself, the server's
# auto_updates.takes). So it may carry nothing a person or an agent must change for, and a migration
# guide is exactly that: a change that needs one bumps the breaking part -- the minor below 1.0, the
# major from 1.0 -- and waits for the person's click.
if version_installs_itself "$base_version" "$version"; then
  migrations="$(git diff --name-only --diff-filter=ACMR "$base" HEAD -- docs/migrations)"
  if [ -n "$migrations" ]; then
    echo "VERSION $version is a $(version_bump "$base_version" "$version") release, which installs itself on every device, but this" >&2
    echo "pull request adds or changes a migration guide:" >&2
    echo "$migrations" | sed 's/^/  /' >&2
    if [ "$(breaking_part "$base_version")" = major ]; then
      echo "A change people must migrate for is a major release from 1.0: scripts/release/bump-version.sh major." >&2
    else
      echo "A change people must migrate for is a minor release below 1.0: scripts/release/bump-version.sh minor." >&2
    fi
    exit 1
  fi
fi

# Publish Release starts on a push that changes VERSION, and GitHub matches a push's paths
# against its first 300 changed files only: a release that changes more might never start it.
changed="$(git diff --name-only "$base" HEAD | wc -l | tr -d '[:space:]')"
if [ "$changed" -gt 300 ]; then
  echo "This pull request changes $changed files. GitHub starts Publish Release from the first 300" >&2
  echo "files a push changes, so merging it might release nothing. Leave VERSION alone here, and" >&2
  echo "release after the merge: gh workflow run release-prepare.yml --ref main -f bump=<part>." >&2
  exit 1
fi

echo "This pull request releases $version (the target branch is at $base_version)."
echo "Merging it releases it: Publish Release uploads the four projects at $version to PyPI, then moves the latest branch."
