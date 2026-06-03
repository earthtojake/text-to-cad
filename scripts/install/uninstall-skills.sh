#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
SKILLS_ROOT="$(cd "$REPO_ROOT/skills" && pwd -P)"
LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"
SKILL_IDS=()
while IFS= read -r skill; do
  SKILL_IDS+=("$skill")
done < <("$LIST_SKILLS_SCRIPT")

ALL_AGENTS=(
  codex
  claude
  gemini
  universal
  project
)

SELECTED_AGENTS=()
DRY_RUN=0
PRUNE_EMPTY=1

usage() {
  cat <<'EOF'
Usage:
  scripts/install/uninstall-skills.sh [--agent <agent>]... [--all] [--dry-run] [--keep-empty-dirs]
  scripts/install/uninstall-skills.sh --list-agents

Removes local development skill links that point back to this checkout. Existing
non-symlink skills and symlinks to other locations are left untouched.

Agents:
  codex             ${CODEX_HOME:-$HOME/.codex}/skills
  claude            ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills
  gemini            $HOME/.gemini/skills
  universal         ${XDG_CONFIG_HOME:-$HOME/.config}/agents/skills
  project           .agents/skills in this repository

Aliases:
  claude-code -> claude
  gemini-cli  -> gemini
  agents      -> universal
  repo        -> project

Options:
  -a, --agent        Remove links for one agent. May be repeated.
  --all             Remove links for every supported agent above.
  --dry-run         Print actions without changing files.
  --keep-empty-dirs Leave empty skill destination directories in place.
  --list-agents     Show resolved destination paths.
  -h, --help        Show this help.

With no --agent or --all, the script removes Codex links.
EOF
}

agent_destination() {
  case "$1" in
    codex)
      printf '%s\n' "${CODEX_HOME:-$HOME/.codex}/skills"
      ;;
    claude)
      printf '%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
      ;;
    gemini)
      printf '%s\n' "$HOME/.gemini/skills"
      ;;
    universal)
      printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/agents/skills"
      ;;
    project)
      printf '%s\n' "$REPO_ROOT/.agents/skills"
      ;;
    *)
      return 1
      ;;
  esac
}

canonical_agent() {
  case "$1" in
    codex) printf 'codex\n' ;;
    claude|claude-code) printf 'claude\n' ;;
    gemini|gemini-cli) printf 'gemini\n' ;;
    universal|agents) printf 'universal\n' ;;
    project|repo) printf 'project\n' ;;
    *)
      echo "Unknown agent: $1" >&2
      return 1
      ;;
  esac
}

contains_value() {
  local needle="$1"
  shift
  local value
  for value in "$@"; do
    if [ "$value" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

add_agent() {
  local agent
  agent="$(canonical_agent "$1")"
  if [ "${#SELECTED_AGENTS[@]}" -eq 0 ] || ! contains_value "$agent" "${SELECTED_AGENTS[@]}"; then
    SELECTED_AGENTS+=("$agent")
  fi
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

resolve_link_dir() {
  local link="$1"
  local target
  local link_dir
  target="$(readlink "$link")"
  if [[ "$target" = /* ]]; then
    cd "$target" && pwd -P
  else
    link_dir="$(cd "$(dirname "$link")" && pwd -P)"
    cd "$link_dir/$target" && pwd -P
  fi
}

remove_skill_link() {
  local skill="$1"
  local destination="$2"
  local source="$SKILLS_ROOT/$skill"
  local link="$destination/$skill"
  local resolved

  if [ -L "$link" ]; then
    resolved="$(resolve_link_dir "$link" 2>/dev/null || true)"
    if [ "$resolved" = "$source" ]; then
      run rm "$link"
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "would remove: $link"
      else
        echo "removed: $link"
      fi
      return
    fi
    echo "skipping non-repo skill symlink: $link -> $(readlink "$link")"
    return
  fi

  if [ -e "$link" ]; then
    echo "skipping existing non-symlink path: $link"
    return
  fi

  echo "ok: no link at $link"
}

prune_empty_destination() {
  local destination="$1"
  if [ "$PRUNE_EMPTY" -eq 0 ] || [ ! -d "$destination" ] || [ -L "$destination" ]; then
    return
  fi
  if [ -z "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    run rmdir "$destination"
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "would remove empty directory: $destination"
    else
      echo "removed empty directory: $destination"
    fi
  fi
}

uninstall_for_agent() {
  local agent="$1"
  local destination
  local resolved
  local skill

  destination="$(agent_destination "$agent")"
  echo "Removing $agent skill links from $destination"

  if [ -L "$destination" ]; then
    resolved="$(resolve_link_dir "$destination" 2>/dev/null || true)"
    if [ "$resolved" = "$SKILLS_ROOT" ]; then
      run rm "$destination"
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "would remove whole-directory skills link: $destination"
      else
        echo "removed whole-directory skills link: $destination"
      fi
    else
      echo "skipping non-repo destination symlink: $destination -> $(readlink "$destination")"
    fi
    return
  fi

  if [ ! -e "$destination" ]; then
    echo "ok: no skill directory at $destination"
    return
  fi

  if [ ! -d "$destination" ]; then
    echo "skipping non-directory destination: $destination"
    return
  fi

  for skill in "${SKILL_IDS[@]}"; do
    remove_skill_link "$skill" "$destination"
  done

  prune_empty_destination "$destination"
}

list_agents() {
  local agent
  for agent in "${ALL_AGENTS[@]}"; do
    printf '%-10s %s\n' "$agent" "$(agent_destination "$agent")"
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -a|--agent)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      add_agent "$2"
      shift
      ;;
    --all)
      SELECTED_AGENTS=()
      for agent in "${ALL_AGENTS[@]}"; do
        add_agent "$agent"
      done
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --keep-empty-dirs)
      PRUNE_EMPTY=0
      ;;
    --list-agents)
      list_agents
      exit 0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ "${#SELECTED_AGENTS[@]}" -eq 0 ]; then
  add_agent codex
fi

for agent in "${SELECTED_AGENTS[@]}"; do
  uninstall_for_agent "$agent"
done
