#!/usr/bin/env bash
set -euo pipefail

# Verify a prepared publish tree is what `main` is allowed to carry.
#
# The contract (CONTRIBUTING.md, "Branch Layouts"): `main` is `develop` with
# versions stamped, skill requirements pinned, and ONLY models/ removed. This runs in the Release workflow after
# scripts/release/prepare-publish-tree.sh and pin-cadgen-requirements.sh, right
# before the publish commit, over the files that commit will contain -- the
# index plus untracked files that .gitignore does not exclude, which is exactly
# what `git add -A` stages. Locally, run it in a scratch worktree after
# bundle.sh --clean and prepare-publish-tree.sh.
#
# Checks:
#   1. the removed roots are absent (prepare-publish-tree.sh --print-removed-roots);
#   2. the source roots that used to be trimmed are present -- apps/, packages/,
#      tests/, requirements-dev.txt -- so a stale trim cannot come back silently;
#   3. NO symlink anywhere in what ships. Codex `plugin add` drops symlinks with
#      no error (scripts/github-workflows/check-builds.sh has the details), so
#      one that reaches main ships a broken skill to every Codex user;
#   4. no sourcemaps, bytecode, node_modules or tests ship inside a skill;
#   5. NO LFS-tracked path ships, apart from the README demo media under assets/.
#      Installers clone without git-lfs and receive pointer files; for a skill
#      fixture or a runtime asset that is a silently broken install. The README
#      gifs are the one accepted exception: 17-26 MB each, decoration only, and
#      GitHub renders LFS media in the README regardless;
#   6. no skill SOURCE reaches into a repo root (../../../packages/, apps/,
#      tests/, models/). packages/ being present on main is not permission to
#      import from it: the Skills CLI installs skills/<name> alone, so the
#      sibling is not there.
#
# Usage: scripts/github-workflows/check-publish-tree.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${PUBLISH_TREE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PREPARE_SCRIPT="$SCRIPT_DIR/../release/prepare-publish-tree.sh"

# README demo media: the one LFS family allowed on main. Keep this list short and
# every entry a deliberate decision.
LFS_ALLOWED_PREFIXES=(assets/)

cd "$REPO_ROOT"

failures=0
fail() {
  echo "FAIL: $*" >&2
  failures=$((failures + 1))
}

# Everything `git add -A` would put in the publish commit: tracked paths that
# still exist plus untracked paths .gitignore does not exclude.
list_shipping_paths() {
  git ls-files -z --cached --others --exclude-standard |
    while IFS= read -r -d '' path; do
      if [ -e "$path" ] || [ -L "$path" ]; then
        printf '%s\n' "$path"
      fi
    done |
    LC_ALL=C sort -u
}

paths_file="$(mktemp)"
trap 'rm -f "$paths_file"' EXIT
list_shipping_paths > "$paths_file"
if [ ! -s "$paths_file" ]; then
  fail "no files found; is $REPO_ROOT a git checkout?"
  exit 1
fi

echo "==> Removed roots are absent"
while IFS= read -r root; do
  [ -n "$root" ] || continue
  if [ -e "$root" ] || [ -L "$root" ]; then
    fail "$root/ must not be present in the publish tree"
  elif grep -q "^$root/" "$paths_file"; then
    fail "$root/ still has shipping paths"
  else
    echo "    $root/ absent"
  fi
done < <("$PREPARE_SCRIPT" --print-removed-roots)

echo "==> Source roots ship (main is develop minus models/)"
for marker in \
  apps/viewer/package.json \
  apps/docs/package.json \
  packages/cadgen/pyproject.toml \
  packages/cadgen/src/cadgen/viewer/main.py \
  packages/cadgen-js/package.json \
  tests/python \
  requirements-dev.txt \
  skills \
  docs \
  VERSION; do
  if [ -e "$marker" ]; then
    echo "    $marker"
  else
    fail "missing from the publish tree: $marker"
  fi
done

echo "==> No symlink ships"
symlinks=0
while IFS= read -r path; do
  if [ -L "$path" ]; then
    fail "symlink in the publish tree: $path -> $(readlink "$path")"
    symlinks=$((symlinks + 1))
  fi
done < "$paths_file"
[ "$symlinks" -eq 0 ] && echo "    none"

echo "==> Skills ship no build or test leftovers"
if grep -E '^skills/.*(\.map|/__pycache__/|\.pyc|/node_modules/|/tests?/)' "$paths_file" > "$paths_file.skill-junk"; then
  fail "skills/ ships build or test leftovers:"
  sed 's/^/      /' "$paths_file.skill-junk" >&2
else
  echo "    none"
fi
rm -f "$paths_file.skill-junk"

echo "==> No LFS-tracked path ships (README media under assets/ excepted)"
lfs_attr="$(git check-attr --stdin filter < "$paths_file" | sed -n 's/: filter: lfs$//p')"
lfs_pointers="$(tr '\n' '\0' < "$paths_file" |
  xargs -0 grep -l --max-count=1 '^version https://git-lfs.github.com/spec/' 2>/dev/null || true)"
lfs_hits="$(printf '%s\n%s\n' "$lfs_attr" "$lfs_pointers" | sed '/^$/d' | LC_ALL=C sort -u)"
lfs_bad=0
while IFS= read -r path; do
  [ -n "$path" ] || continue
  allowed=0
  for prefix in "${LFS_ALLOWED_PREFIXES[@]}"; do
    case "$path" in "$prefix"*) allowed=1 ;; esac
  done
  if [ "$allowed" -eq 1 ]; then
    echo "    allowed: $path"
  else
    fail "LFS-tracked path in the publish tree (installers clone without git-lfs): $path"
    lfs_bad=$((lfs_bad + 1))
  fi
done <<< "$lfs_hits"
[ "$lfs_bad" -eq 0 ] && echo "    no LFS path outside ${LFS_ALLOWED_PREFIXES[*]}"

echo "==> No skill source reaches a repo root"
skill_root_refs="$(
  grep -rIlE '\.\./\.\./\.\./(packages|apps|tests|models)/|["'"'"']\.\./\.\./(packages|apps|tests|models)/' skills \
    --exclude-dir=node_modules 2>/dev/null || true
)"
if [ -n "$skill_root_refs" ]; then
  fail "a skill reaches into a repo root; an installed skill has no siblings (the Skills CLI copies skills/<name> alone):"
  printf '%s\n' "$skill_root_refs" | sed 's/^/      /' >&2
else
  echo "    none"
fi

if [ "$failures" -ne 0 ]; then
  echo "" >&2
  echo "Publish tree check failed ($failures problem(s))." >&2
  exit 1
fi
echo "Publish tree is valid: $(wc -l < "$paths_file" | tr -d ' ') paths ship."
