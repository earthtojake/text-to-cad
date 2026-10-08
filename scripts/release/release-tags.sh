#!/usr/bin/env bash
# Release tag naming, shared by the release scripts and the release workflows.
#
# Tags are `v<VERSION>` from 0.5.0 onward. Releases before that were tagged bare
# (`0.4.28`), and tags are permanent, so anything that asks "what is the latest
# release" has to see BOTH spellings and compare the versions behind them, never
# the tag strings: git's own version sort would rank every `v` tag above every
# bare one on the letter alone.
#
# Source this file, then:
#   release_tag_name 0.5.0            -> v0.5.0
#   version_from_release_tag v0.5.0   -> 0.5.0   (bare tags pass through)
#   latest_release_tag                -> the tag (either spelling) with the highest version, or ""
#   version_greater 0.5.1 0.5.0       -> succeeds when the first X.Y.Z is the greater
#
# shellcheck shell=bash

release_tag_name() {
  printf 'v%s\n' "$1"
}

version_from_release_tag() {
  printf '%s\n' "${1#v}"
}

# All release tags, either spelling, one per line -- via `git tag --list` in the
# caller's repository (or RELEASE_TAGS_GIT_DIR).
release_tags() {
  git ${RELEASE_TAGS_GIT_DIR:+-C "$RELEASE_TAGS_GIT_DIR"} tag --list \
    'v[0-9]*.[0-9]*.[0-9]*' '[0-9]*.[0-9]*.[0-9]*'
}

# The tag naming the highest version. Sorted on the version with the prefix
# stripped (numeric, field by field), so `v0.5.0` beats `0.4.28` because 5 > 4,
# not because v > 0.
latest_release_tag() {
  release_tags |
    while IFS= read -r tag; do
      [ -n "$tag" ] || continue
      version="$(version_from_release_tag "$tag")"
      case "$version" in
        *[!0-9.]*|"") continue ;;  # not a plain X.Y.Z
      esac
      printf '%s %s\n' "$version" "$tag"
    done |
    sort -t. -k1,1n -k2,2n -k3,3n |
    tail -n 1 |
    cut -d' ' -f2-
}

# Numeric, field by field: 0.10.0 is greater than 0.9.9. Both arguments are plain X.Y.Z.
version_greater() {
  local left_major left_minor left_patch right_major right_minor right_patch
  IFS=. read -r left_major left_minor left_patch <<< "$1"
  IFS=. read -r right_major right_minor right_patch <<< "$2"
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
