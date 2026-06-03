#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${RELEASE_REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

SOURCE_REF="HEAD"
TARGET_REF="origin/main"
PRINT_PREVIOUS_SOURCE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/release/check-publish-source.sh [--source-ref REF] [--target-ref REF]
  scripts/release/check-publish-source.sh --print-previous-source [--target-ref REF]

Checks that a publish source contains the source commit used by the previous
publish target. This keeps main as a generated-output branch without requiring
develop to merge generated publish commits back into source history.

Options:
  --source-ref REF           Source branch, tag, or SHA to publish. Defaults to HEAD.
  --target-ref REF           Previous publish target ref. Defaults to origin/main.
  --print-previous-source    Print only the resolved previous source commit.
  -h, --help                 Show this help.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

resolve_commit() {
  local ref="$1"
  local label="$2"
  local commit
  commit="$(git rev-parse --verify "$ref^{commit}" 2>/dev/null)" ||
    die "could not resolve $label ref as a commit: $ref"
  printf '%s\n' "$commit"
}

source_commit_from_message() {
  local target_commit="$1"
  local recorded
  recorded="$(
    git log -1 --format=%B "$target_commit" |
      sed -nE 's/^Source commit:[[:space:]]*([0-9a-fA-F]{7,64})[[:space:]]*$/\1/p' |
      head -n 1
  )"
  [ -n "$recorded" ] || return 1
  resolve_commit "$recorded" "recorded source"
}

previous_source_for_target() {
  local target_commit="$1"
  local previous_source

  if previous_source="$(source_commit_from_message "$target_commit")"; then
    printf '%s\n' "$previous_source"
    return 0
  fi

  if git rev-parse --verify --quiet "$target_commit^" >/dev/null; then
    git rev-parse "$target_commit^"
    return 0
  fi

  die "could not determine previous publish source for $TARGET_REF; expected a Source commit line or a parent commit"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-ref)
      [ "$#" -ge 2 ] || die "--source-ref requires a value"
      SOURCE_REF="$2"
      shift
      ;;
    --source-ref=*)
      SOURCE_REF="${1#--source-ref=}"
      ;;
    --target-ref)
      [ "$#" -ge 2 ] || die "--target-ref requires a value"
      TARGET_REF="$2"
      shift
      ;;
    --target-ref=*)
      TARGET_REF="${1#--target-ref=}"
      ;;
    --print-previous-source)
      PRINT_PREVIOUS_SOURCE=1
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

source_sha="$(resolve_commit "$SOURCE_REF" "source")"
target_sha="$(resolve_commit "$TARGET_REF" "target")"
previous_source="$(previous_source_for_target "$target_sha")"

if [ "$PRINT_PREVIOUS_SOURCE" -eq 1 ]; then
  printf '%s\n' "$previous_source"
  exit 0
fi

if ! git merge-base --is-ancestor "$previous_source" "$source_sha"; then
  {
    echo "previous publish source is not an ancestor of the requested source"
    echo "target ref: $TARGET_REF"
    echo "target commit: $target_sha"
    echo "previous source: $previous_source"
    echo "requested source: $source_sha"
    echo
    echo "Use source_ref=develop after the release PR has merged, or rebase/merge the source branch so it contains the previous release source."
  } >&2
  exit 1
fi

echo "Publish source is valid: $source_sha contains previous publish source $previous_source from $TARGET_REF."
