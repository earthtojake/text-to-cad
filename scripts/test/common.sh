#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

section() {
  printf '\n==> %s\n' "$1"
}

run_python_unittest() {
  local name="$1"
  local start_dir="$2"
  shift 2
  local test_files=()
  local python_path="$REPO_ROOT:$REPO_ROOT/$start_dir"
  local path_entry

  section "$name"

  while IFS= read -r test_file; do
    test_files+=("$test_file")
  done < <(find "$REPO_ROOT/$start_dir" -name 'test*.py' -print | sort)

  if [ "${#test_files[@]}" -eq 0 ]; then
    echo "No Python tests found under $start_dir"
    return 0
  fi

  for path_entry in "$@"; do
    if [[ "$path_entry" = /* ]]; then
      python_path="$python_path:$path_entry"
    else
      python_path="$python_path:$REPO_ROOT/$path_entry"
    fi
  done

  PYTHONPATH="$python_path${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" -m unittest "${test_files[@]}"
}
