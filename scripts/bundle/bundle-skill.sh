#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL_BUNDLE_DIR="$SCRIPT_DIR/skills"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-skill.sh <skill-id> [skill-bundle-args...]
  scripts/bundle/bundle-skill.sh --all [shared-skill-bundle-args...]

Runs bundle logic for one skill. Skill IDs map to
scripts/bundle/skills/bundle-<skill-id>.sh.

Options:
  --all       Run every skill bundle script under scripts/bundle/skills.
  -h, --help  Show this help.

Skill-specific arguments are passed through to the selected bundle script.
If a skill has no bundle script, this command fails.
EOF
}

list_bundleable_skills() {
  find "$SKILL_BUNDLE_DIR" -maxdepth 1 -type f -name 'bundle-*.sh' -print |
    while IFS= read -r script; do
      basename "$script" | sed -e 's/^bundle-//' -e 's/\.sh$//'
    done |
    LC_ALL=C sort
}

run_skill_bundle() {
  local skill_id="$1"
  shift
  local bundle_script="$SKILL_BUNDLE_DIR/bundle-$skill_id.sh"

  if [ ! -f "$REPO_ROOT/skills/$skill_id/SKILL.md" ]; then
    echo "Unknown skill: $skill_id" >&2
    echo "Known skills:" >&2
    "$REPO_ROOT/scripts/utils/list-skills.sh" | sed 's/^/- /' >&2
    exit 1
  fi

  if [ ! -x "$bundle_script" ]; then
    echo "Skill has no bundle logic: $skill_id" >&2
    echo "Expected bundle script: ${bundle_script#$REPO_ROOT/}" >&2
    exit 1
  fi

  "$bundle_script" "$@"
}

if [ "$#" -eq 0 ]; then
  usage >&2
  exit 2
fi

case "$1" in
  -h|--help)
    usage
    exit 0
    ;;
  --all)
    shift
    while IFS= read -r skill_id; do
      run_skill_bundle "$skill_id" "$@"
    done < <(list_bundleable_skills)
    ;;
  -*)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 2
    ;;
  *)
    skill_id="$1"
    shift
    run_skill_bundle "$skill_id" "$@"
    ;;
esac
