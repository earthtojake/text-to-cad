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
DESTINATION_WOULD_REPLACE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/install/install-skills.sh [--agent <agent>]... [--all] [--dry-run]
  scripts/install/install-skills.sh --list-agents

Installs per-skill symlinks from this checkout's skills/ directory into local
agent skill directories. Existing matching symlinks are left alone.

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
  -a, --agent       Install links for one agent. May be repeated.
  --all            Install links for every supported agent above.
  --dry-run        Print actions without changing files.
  --list-agents    Show resolved destination paths.
  -h, --help       Show this help.

With no --agent or --all, the script installs Codex links.
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

contains_agent() {
  local needle="$1"
  local agent
  if [ "${#SELECTED_AGENTS[@]}" -eq 0 ]; then
    return 1
  fi
  for agent in "${SELECTED_AGENTS[@]}"; do
    if [ "$agent" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

add_agent() {
  local agent
  agent="$(canonical_agent "$1")"
  if ! contains_agent "$agent"; then
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

prepare_destination() {
  local destination="$1"
  local resolved
  DESTINATION_WOULD_REPLACE=0
  if [ -L "$destination" ]; then
    resolved="$(resolve_link_dir "$destination" 2>/dev/null || true)"
    if [ "$resolved" = "$SKILLS_ROOT" ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "would replace whole-directory skills link with per-skill link directory: $destination"
        DESTINATION_WOULD_REPLACE=1
      else
        echo "Replacing whole-directory skills link with per-skill link directory: $destination"
      fi
      run rm "$destination"
    else
      echo "Refusing to replace destination symlink: $destination -> $(readlink "$destination")" >&2
      echo "Remove it manually or choose another agent destination." >&2
      exit 1
    fi
  fi

  if [ -e "$destination" ] && [ ! -d "$destination" ]; then
    echo "Destination exists but is not a directory: $destination" >&2
    exit 1
  fi

  run mkdir -p "$destination"
}

install_skill_link() {
  local skill="$1"
  local destination="$2"
  local source="$SKILLS_ROOT/$skill"
  local link="$destination/$skill"
  local resolved

  if [ ! -d "$source" ]; then
    echo "Missing supported skill directory: $source" >&2
    exit 1
  fi

  if [ -L "$link" ]; then
    resolved="$(resolve_link_dir "$link" 2>/dev/null || true)"
    if [ "$resolved" = "$source" ]; then
      echo "ok: $link -> $source"
      return
    fi
    run rm "$link"
  elif [ -e "$link" ]; then
    echo "Skipping existing non-symlink path: $link" >&2
    return
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    run ln -s "$source" "$link"
    echo "would link: $link -> $source"
  else
    run ln -s "$source" "$link"
    echo "linked: $link -> $source"
  fi
}

install_for_agent() {
  local agent="$1"
  local destination
  local skill

  destination="$(agent_destination "$agent")"
  echo "Installing $agent skill links into $destination"
  prepare_destination "$destination"

  if [ "$DRY_RUN" -eq 1 ] && [ "$DESTINATION_WOULD_REPLACE" -eq 1 ]; then
    for skill in "${SKILL_IDS[@]}"; do
      echo "would link: $destination/$skill -> $SKILLS_ROOT/$skill"
    done
    return
  fi

  for skill in "${SKILL_IDS[@]}"; do
    install_skill_link "$skill" "$destination"
  done

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
  install_for_agent "$agent"
done
