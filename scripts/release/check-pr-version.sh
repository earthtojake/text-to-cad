#!/usr/bin/env bash
set -euo pipefail

# Run in a checkout with the target branch's remote history available. The
# pull-request event's base SHA can remain an old snapshot after main releases.
# Compare changes introduced by the branch, excluding releases it inherited.
base_ref="${1:?Usage: check-pr-version.sh <base-ref> <head-ref> <head-sha>}"
head_ref="${2:?Missing head ref}"
head_sha="${3:?Missing head SHA}"
base_sha="$(git merge-base "refs/remotes/origin/$base_ref" "$head_sha")"

if git diff --quiet "$base_sha" "$head_sha" -- VERSION; then
  echo "VERSION unchanged by this PR."
  exit 0
fi

case "$head_ref" in
  release/*) echo "VERSION changed on $head_ref (a release PR)." ;;
  *)
    echo "This PR changes VERSION but its branch is '$head_ref', not release/*." >&2
    echo "Version bumps come from the Prepare Release workflow:" >&2
    echo "  gh workflow run release-prepare.yml --ref main -f bump=patch" >&2
    exit 1
    ;;
esac
