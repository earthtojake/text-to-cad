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
#   version_bump 0.11.3 0.12.0        -> minor: the part the second moves on (fails when it is no later)
#   breaking_part 0.11.3              -> minor: the part a breaking change bumps (major from 1.0)
#   version_installs_itself 1.4.2 1.5.0 -> succeeds when a device at the first takes the second itself
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

# The part of the first X.Y.Z that the second moves on: major, minor or patch. Prints nothing and
# fails when the second is not the later.
version_bump() {
  local have_major have_minor want_major want_minor
  version_greater "$2" "$1" || return 1
  IFS=. read -r have_major have_minor _ <<< "$1"
  IFS=. read -r want_major want_minor _ <<< "$2"
  if [ "$((10#$want_major))" -ne "$((10#$have_major))" ]; then
    echo major
  elif [ "$((10#$want_minor))" -ne "$((10#$have_minor))" ]; then
    echo minor
  else
    echo patch
  fi
}

# The part a breaking change bumps from an X.Y.Z, as Semantic Versioning numbers releases: the major
# from 1.0, and below 1.0, which the standard leaves to the project, the minor.
breaking_part() {
  local major
  IFS=. read -r major _ <<< "$1"
  if [ "$((10#$major))" -ge 1 ]; then echo major; else echo minor; fi
}

# Whether a device at the first X.Y.Z installs the second by itself, with automatic updates on: a later
# release that keeps the breaking part -- a patch below 1.0, a patch or minor from 1.0. The server's
# auto_updates.takes is the rule; tests/python/global/test_pr_version_guard.py holds this copy to it.
version_installs_itself() {
  local bump
  bump="$(version_bump "$1" "$2")" || return 1
  [ "$bump" = patch ] || { [ "$bump" = minor ] && [ "$(breaking_part "$1")" = major ]; }
}

# A version PyPI will never take: the PyPI project `cad` published it before it was transferred to this
# project (scripts/release/unavailable-versions.txt). A trailing `.0` is insignificant to PyPI, so the
# comparison drops trailing `.0` parts from both sides (`1.0.0` is the listed `1.0`).
#   refuse_unavailable_version 0.9.0  -> prints the refusal on stderr and fails; succeeds otherwise
UNAVAILABLE_VERSIONS_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/unavailable-versions.txt"

_release_without_trailing_zeros() {
  local version="$1"
  while [[ "$version" == *.0 ]]; do version="${version%.0}"; done
  printf '%s\n' "$version"
}

refuse_unavailable_version() {
  local version="$1" want listed
  [ -f "$UNAVAILABLE_VERSIONS_FILE" ] || {
    echo "missing scripts/release/unavailable-versions.txt" >&2
    return 1
  }
  want="$(_release_without_trailing_zeros "$version")"
  while IFS= read -r listed; do
    listed="${listed%%#*}"
    listed="${listed//[[:space:]]/}"
    [ -n "$listed" ] || continue
    if [ "$(_release_without_trailing_zeros "$listed")" = "$want" ]; then
      echo "$version is not available: the PyPI project cad published it before the transfer (scripts/release/unavailable-versions.txt)" >&2
      return 1
    fi
  done < "$UNAVAILABLE_VERSIONS_FILE"
  return 0
}
