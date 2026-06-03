#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILLS_ROOT="$REPO_ROOT/skills"

if [ ! -d "$SKILLS_ROOT" ]; then
  echo "Missing skills directory: $SKILLS_ROOT" >&2
  exit 1
fi

find "$SKILLS_ROOT" -mindepth 1 -maxdepth 1 -type d -print |
  while IFS= read -r skill_dir; do
    if [ -f "$skill_dir/SKILL.md" ]; then
      basename "$skill_dir"
    fi
  done |
  LC_ALL=C sort
