#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL_SYMLINK_DIR="$SCRIPT_DIR/skills"

usage() {
  cat <<'EOF'
Usage:
  scripts/dev/setup-skill-symlink.sh <skill-id> [skill-symlink-args...]
  scripts/dev/setup-skill-symlink.sh --all [shared-skill-symlink-args...]

Sets up development symlinks for one skill. Skill IDs map to
scripts/dev/skills/setup-<skill-id>-skill-symlink.sh.

Options:
  --all       Run every skill symlink setup script under scripts/dev/skills.
  -h, --help  Show this help.

Skill-specific arguments are passed through to the selected setup script.
If a skill has no symlink setup script, this command fails.
EOF
}

list_linkable_skills() {
  find "$SKILL_SYMLINK_DIR" -maxdepth 1 -type f -name 'setup-*-skill-symlink.sh' -print |
    while IFS= read -r script; do
      basename "$script" | sed -e 's/^setup-//' -e 's/-skill-symlink\.sh$//'
    done |
    LC_ALL=C sort
}

run_skill_setup() {
  local skill_id="$1"
  shift
  local setup_script="$SKILL_SYMLINK_DIR/setup-$skill_id-skill-symlink.sh"

  if [ ! -f "$REPO_ROOT/skills/$skill_id/SKILL.md" ]; then
    echo "Unknown skill: $skill_id" >&2
    echo "Known skills:" >&2
    "$REPO_ROOT/scripts/utils/list-skills.sh" | sed 's/^/- /' >&2
    exit 1
  fi

  if [ ! -x "$setup_script" ]; then
    echo "Skill has no development symlink setup: $skill_id" >&2
    echo "Expected setup script: ${setup_script#$REPO_ROOT/}" >&2
    exit 1
  fi

  "$setup_script" "$@"
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
      run_skill_setup "$skill_id" "$@"
    done < <(list_linkable_skills)
    ;;
  -*)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 2
    ;;
  *)
    skill_id="$1"
    shift
    run_skill_setup "$skill_id" "$@"
    ;;
esac
