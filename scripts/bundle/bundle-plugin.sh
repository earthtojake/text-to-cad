#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="write"
CLEAN=0

SOURCE_SKILLS_ROOT="$REPO_ROOT/skills"
PLUGIN_ROOT="$REPO_ROOT/plugins/cad"
TARGET_SKILLS_ROOT="$PLUGIN_ROOT/skills"
CHECK_DIR="${PLUGIN_BUNDLE_CHECK_DIR:-${PLUGIN_BUILD_CHECK_DIR:-$REPO_ROOT/tmp/plugin-cad-check}}"
LIST_SKILLS_SCRIPT="$REPO_ROOT/scripts/utils/list-skills.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  scripts/bundle/bundle-plugin.sh [--check] [--clean]

Bundles the installable cad plugin package by copying the root skills/
sources into plugins/cad/skills. The plugin package must not contain symlinks
because provider installers cache plugin roots independently of this checkout.

Options:
  --check  Bundle into tmp/ and fail if plugin outputs or metadata are stale.
  --clean  Remove temporary bundle/check directories first.
  -h, --help
           Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      MODE="check"
      ;;
    --clean)
      CLEAN=1
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

ensure_deps() {
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync is required to bundle plugin skill copies." >&2
    exit 1
  fi
  if [ ! -d "$SOURCE_SKILLS_ROOT" ]; then
    echo "Missing source skills directory: $SOURCE_SKILLS_ROOT" >&2
    exit 1
  fi
  if [ ! -d "$PLUGIN_ROOT" ]; then
    echo "Missing plugin directory: $PLUGIN_ROOT" >&2
    exit 1
  fi
  if [ ! -x "$LIST_SKILLS_SCRIPT" ]; then
    echo "Missing skill list script: $LIST_SKILLS_SCRIPT" >&2
    exit 1
  fi
}

list_skills() {
  "$LIST_SKILLS_SCRIPT"
}

assert_no_symlinks() {
  local target_dir="$1"
  local first_link
  first_link="$(find "$target_dir" -type l -print -quit)"
  if [ -n "$first_link" ]; then
    echo "Plugin skill copy contains a symlink: $first_link" >&2
    echo "Run scripts/bundle/bundle-plugin.sh to bundle plugin skill copies." >&2
    exit 1
  fi
}

sync_skills() {
  local target_root="$1"
  local skill

  rm -rf "$target_root"
  mkdir -p "$target_root"

  while IFS= read -r skill; do
    local source_dir="$SOURCE_SKILLS_ROOT/$skill"
    local target_dir="$target_root/$skill"
    if [ ! -d "$source_dir" ]; then
      echo "Missing source skill directory: skills/$skill" >&2
      exit 1
    fi
    if [ ! -f "$source_dir/SKILL.md" ]; then
      echo "Missing source skill manifest: skills/$skill/SKILL.md" >&2
      exit 1
    fi
    mkdir -p "$target_dir"
    rsync -aL --delete \
      --delete-excluded \
      --exclude __pycache__ \
      --exclude .pytest_cache \
      --exclude '*.pyc' \
      --exclude tests \
      --exclude __tests__ \
      --exclude 'test_*.py' \
      --exclude '*_test.py' \
      --exclude '*.test.js' \
      --exclude '*.test.mjs' \
      --exclude '*.test.ts' \
      --exclude '*.test.tsx' \
      --exclude '*.spec.js' \
      --exclude '*.spec.mjs' \
      --exclude '*.spec.ts' \
      --exclude '*.spec.tsx' \
      "$source_dir/" "$target_dir/"
  done < <(list_skills)

  assert_no_symlinks "$target_root"
}

check_skill_names() {
  local target_root="$1"
  local expected actual
  expected="$(list_skills)"
  actual="$(find "$target_root" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; | sort)"
  if [ "$actual" != "$expected" ]; then
    echo "Plugin skill list is stale." >&2
    echo "Expected:" >&2
    printf '%s\n' "$expected" >&2
    echo "Actual:" >&2
    printf '%s\n' "$actual" >&2
    exit 1
  fi
}

check_skills() {
  local check_skills_root="$CHECK_DIR/skills"
  local first_link

  if [ ! -d "$TARGET_SKILLS_ROOT" ]; then
    echo "Missing generated plugin skill copy: plugins/cad/skills" >&2
    echo "Run scripts/bundle/bundle-plugin.sh and commit plugins/cad/skills." >&2
    exit 1
  fi

  first_link="$(find "$TARGET_SKILLS_ROOT" -type l -print -quit)"
  if [ -n "$first_link" ]; then
    "$REPO_ROOT/scripts/dev/setup-plugin-symlink.sh" --check
    echo "Plugin skill copy is in development symlink layout; production copy freshness is checked on build-test/main."
    return
  fi

  assert_no_symlinks "$TARGET_SKILLS_ROOT"
  check_skill_names "$TARGET_SKILLS_ROOT"

  if ! diff -qr \
    -x __pycache__ \
    -x .pytest_cache \
    -x '*.pyc' \
    "$check_skills_root" "$TARGET_SKILLS_ROOT" >/tmp/plugin-cad-skills-diff.txt; then
    cat /tmp/plugin-cad-skills-diff.txt >&2
    echo "" >&2
    echo "Plugin skill copy is stale." >&2
    echo "Run scripts/bundle/bundle-plugin.sh and commit plugins/cad/skills." >&2
    exit 1
  fi

  echo "Plugin skill copy is up to date."
}

validate_plugin() {
  "$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])

plugin_name = "cad"
skills = sorted(
    path.name
    for path in (repo_root / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)

plugin_root = repo_root / "plugins" / plugin_name
codex_manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
claude_manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
claude_marketplace_path = repo_root / ".claude-plugin" / "marketplace.json"
codex_marketplace_path = repo_root / ".codex-plugin" / "marketplace.json"
version_path = plugin_root / "VERSION"
errors: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


require(plugin_root.is_dir(), f"missing plugin directory: {plugin_root}")
require(codex_manifest_path.is_file(), f"missing Codex plugin manifest: {codex_manifest_path}")
require(claude_manifest_path.is_file(), f"missing Claude plugin manifest: {claude_manifest_path}")
require(claude_marketplace_path.is_file(), f"missing Claude marketplace: {claude_marketplace_path}")
require(codex_marketplace_path.is_file(), f"missing Codex marketplace: {codex_marketplace_path}")
require(version_path.is_file(), f"missing plugin version file: {version_path}")


def load_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{path} must contain a JSON object")
        return {}
    return payload


def plugin_version() -> str:
    if not version_path.is_file():
        return ""
    return version_path.read_text(encoding="utf-8").strip()


version = plugin_version()


def validate_plugin_manifest(path: Path, provider: str) -> None:
    manifest = load_json_object(path)
    if not manifest:
        return
    require(manifest.get("name") == plugin_name, f"{provider} plugin manifest name is stale")
    require(manifest.get("version") == version, f"{provider} plugin manifest version is stale")
    require(manifest.get("skills") in {"./skills/", "./skills", "skills"}, f"{provider} plugin manifest must point at ./skills/")


validate_plugin_manifest(codex_manifest_path, "Codex")
validate_plugin_manifest(claude_manifest_path, "Claude")

codex_marketplace = load_json_object(codex_marketplace_path)
if codex_marketplace:
    require(codex_marketplace.get("name") == "text-to-cad", "Codex marketplace name is stale")
    plugins = codex_marketplace.get("plugins")
    if not isinstance(plugins, list):
        errors.append("Codex marketplace plugins must be an array")
    else:
        cad_entries = [
            entry for entry in plugins
            if isinstance(entry, dict) and entry.get("name") == plugin_name
        ]
        require(len(cad_entries) == 1, "Codex marketplace must contain exactly one cad plugin entry")
        if cad_entries:
            source = cad_entries[0].get("source")
            if not isinstance(source, dict):
                errors.append("Codex marketplace cad source must be an object")
            else:
                require(source.get("path") == "./plugins/cad", "Codex marketplace cad source path is stale")

claude_marketplace = load_json_object(claude_marketplace_path)
if claude_marketplace:
    require(claude_marketplace.get("name") == "text-to-cad", "Claude marketplace name is stale")
    require(claude_marketplace.get("version") == version, "Claude marketplace version is stale")
    plugins = claude_marketplace.get("plugins")
    if not isinstance(plugins, list):
        errors.append("Claude marketplace plugins must be an array")
    else:
        cad_entries = [
            entry for entry in plugins
            if isinstance(entry, dict) and entry.get("name") == plugin_name
        ]
        require(len(cad_entries) == 1, "Claude marketplace must contain exactly one cad plugin entry")
        if cad_entries:
            entry = cad_entries[0]
            require(entry.get("source") == "./plugins/cad", "Claude marketplace cad source is stale")
            require(entry.get("version") == version, "Claude marketplace cad version is stale")

skills_root = plugin_root / "skills"
for skill in skills:
    root_skill = repo_root / "skills" / skill
    bundled_skill = skills_root / skill
    require(root_skill.is_dir(), f"missing source skill: {root_skill}")
    require((root_skill / "SKILL.md").is_file(), f"missing source skill manifest: {root_skill / 'SKILL.md'}")
    require(bundled_skill.is_dir(), f"plugin skill copy must be a directory: {bundled_skill}")
    if bundled_skill.is_symlink():
        require(
            bundled_skill.resolve() == root_skill.resolve(),
            f"plugin development symlink points at the wrong skill: {bundled_skill}",
        )
    require((bundled_skill / "SKILL.md").is_file(), f"missing plugin skill manifest: {bundled_skill / 'SKILL.md'}")

if skills_root.is_dir():
    for path in skills_root.rglob("*"):
        if path.is_symlink():
            if path.parent != skills_root:
                errors.append(f"plugin skill copy must not contain nested symlinks: {path}")

if skills_root.is_dir():
    bundled_names = sorted(path.name for path in skills_root.iterdir() if not path.name.startswith("."))
    require(bundled_names == skills, f"cad plugin bundled skill list is stale: {bundled_names}")

if errors:
    print("Plugin validation failed:")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print(f"Plugin validation passed: {plugin_root}")
PY
}

ensure_deps

if [ "$CLEAN" -eq 1 ]; then
  rm -rf "$CHECK_DIR"
fi

if [ "$MODE" = "check" ]; then
  sync_skills "$CHECK_DIR/skills"
  check_skills
  validate_plugin
else
  sync_skills "$TARGET_SKILLS_ROOT"
  echo "Bundled plugins/cad/skills"
fi
