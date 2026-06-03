#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"

cd "$REPO_ROOT"

run_python_unittest "cadpy package Python tests" "tests/python/packages/cadpy" "packages/cadpy/src"
run_python_unittest "cadpy_metadata package Python tests" "tests/python/packages/cadpy_metadata" "packages/cadpy_metadata/src"

while IFS= read -r skill; do
  test_dir="tests/python/skills/$skill"
  if [ -d "$test_dir" ]; then
    run_python_unittest "$skill skill Python tests" "$test_dir" "skills/$skill/scripts"
  fi
done < <("$LIST_SKILLS_SCRIPT")

run_python_unittest "MoveIt2 server Python tests" "tests/python/viewer/moveit2_server" "viewer/moveit2_server"
