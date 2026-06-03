#!/usr/bin/env bash

link_path() {
  local path="$1"
  local target="$2"

  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    echo "Already linked $path -> $target"
    return
  fi

  if [ -e "$path" ] || [ -L "$path" ]; then
    rm -rf "$path"
  fi

  mkdir -p "$(dirname "$path")"
  ln -s "$target" "$path"
  echo "Linked $path -> $target"
}

check_link() {
  local path="$1"
  local expected_target="$2"
  local actual_target

  if [ ! -L "$path" ]; then
    echo "$path must be a symlink to $expected_target" >&2
    return 1
  fi

  actual_target="$(readlink "$path")"
  if [ "$actual_target" != "$expected_target" ]; then
    echo "$path points to $actual_target, expected $expected_target" >&2
    return 1
  fi

  if [ ! -e "$path" ]; then
    echo "$path points to missing target $expected_target" >&2
    return 1
  fi
}

setup_link() {
  local mode="$1"
  local path="$2"
  local target="$3"

  if [ "$mode" = "check" ]; then
    check_link "$path" "$target"
  else
    link_path "$path" "$target"
  fi
}
