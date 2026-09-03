#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

RUN_BUNDLE_CHECK=1

usage() {
  cat <<'EOF'
Usage:
  scripts/github-workflows/check-builds.sh [--skip-bundle-check]

Checks the production bundle layout. By default this also verifies generated
outputs are fresh with scripts/bundle/bundle.sh --check. Use
--skip-bundle-check only after the current workflow has already run
scripts/bundle/bundle.sh --clean in the same checkout.

Options:
  --skip-bundle-check  Skip the generated-output freshness rebuild.
  -h, --help           Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-bundle-check)
      RUN_BUNDLE_CHECK=0
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

# Ask the bundle scripts which paths they generate rather than repeating them
# here, so this check cannot fall behind a new or renamed bundle output.
generated_paths() {
  "$REPO_ROOT/scripts/bundle/bundle-skill.sh" --all --print-outputs
}

check_generated_path() {
  local root="$1"
  local first_link

  if [ ! -e "$root" ]; then
    echo "Missing production bundle path: $root" >&2
    echo "Run scripts/bundle/bundle.sh --clean and commit the generated outputs." >&2
    exit 1
  fi

  # Bundling installs dependencies under some roots; only committed paths matter.
  #
  # This assertion is load-bearing, not tidiness. The three installers each treat
  # symlinks differently, and one of them loses data silently:
  #   - Skills CLI (npx skills): dereferences them into real files.
  #   - Claude Code plugin install: preserves them verbatim.
  #   - Codex plugin add: SILENTLY DROPS them. copy_dir_recursive in
  #     codex-rs/core-plugins/src/store.rs branches only on is_dir()/is_file(),
  #     and DirEntry::file_type() does not traverse symlinks, so a symlinked
  #     entry matches neither branch and never reaches the plugin cache. No
  #     error, no warning -- the file is simply missing at runtime.
  # A symlink that reaches the published tree therefore ships a broken skill to
  # every Codex user. Do not relax this check.
  first_link="$(find "$root" -name node_modules -prune -o -type l -print -quit)"
  if [ -n "$first_link" ]; then
    echo "Production bundle paths must not contain symlinks." >&2
    echo "First symlink: $first_link" >&2
    echo "Run scripts/bundle/bundle.sh --clean and commit the generated outputs." >&2
    exit 1
  fi
}

while IFS= read -r generated_path; do
  check_generated_path "$generated_path"
done < <(generated_paths)

# The generated paths above are cadgen's committed runtime, inside packages/. main is
# the source branch AND what every installer clones, so the rest of the shipping
# contract is checked over the tree itself, here, on every run:
#
#   * no symlink anywhere (tracked): Codex drops them silently -- see above;
#   * no LFS-tracked path under skills/: installers clone without git-lfs and get
#     pointer files, which for a skill fixture or runtime asset is a silently broken
#     install. models/ and assets/ stay LFS: nothing installs them, .lfsconfig keeps
#     them as pointers, and .gitattributes export-ignores models/ from archives;
#   * no skill reaching into a repo root (../../../packages/, apps/, tests/, models/):
#     the Skills CLI installs skills/<name> alone, so the sibling is not there.
check_tree_has_no_symlinks() {
  local links
  links="$(git -C "$REPO_ROOT" ls-files -s | awk '$1 == "120000" { print $4 }')"
  if [ -n "$links" ]; then
    echo "Tracked symlinks would ship to every installer, and Codex plugin installs" >&2
    echo "drop them silently, shipping a skill with missing files:" >&2
    printf '%s\n' "$links" | sed 's/^/  /' >&2
    exit 1
  fi
}

check_skills_have_no_lfs_paths() {
  local hits
  hits="$(git -C "$REPO_ROOT" ls-files skills | git -C "$REPO_ROOT" check-attr --stdin filter |
    sed -n 's/: filter: lfs$//p')"
  if [ -n "$hits" ]; then
    echo "LFS-tracked paths under skills/ (installers clone without git-lfs):" >&2
    printf '%s\n' "$hits" | sed 's/^/  /' >&2
    exit 1
  fi
}

check_skills_do_not_reach_repo_roots() {
  local refs
  refs="$(
    grep -rIlE '\.\./\.\./\.\./(packages|apps|tests|models)/|["'"'"']\.\./\.\./(packages|apps|tests|models)/' \
      "$REPO_ROOT/skills" --exclude-dir=node_modules 2>/dev/null || true
  )"
  if [ -n "$refs" ]; then
    echo "A skill reaches into a repo root; an installed skill has no siblings:" >&2
    printf '%s\n' "$refs" | sed 's/^/  /' >&2
    exit 1
  fi
}

check_tree_has_no_symlinks
check_skills_have_no_lfs_paths
check_skills_do_not_reach_repo_roots

if [ "$RUN_BUNDLE_CHECK" -eq 1 ]; then
  "$REPO_ROOT/scripts/bundle/bundle.sh" --check
else
  echo "Skipping bundle freshness rebuild; current workflow already bundled outputs."
fi

echo "Production bundle layout is valid."
