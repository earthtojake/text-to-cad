#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO_ROOT="$(git -C "$SCRIPT_DIR/../.." rev-parse --show-toplevel)"
DEFAULT_TARGET="../cad-viewer"
TARGET_ARG="$DEFAULT_TARGET"
TARGET_SET=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/viewer/sync-cad-viewer-repo.sh [--dry-run] [target-relative-dir]

Copies the CAD Viewer source repo layout into a separate standalone cad-viewer
git checkout. The target path is resolved relative to this text-to-cad repo.

Default target:
  ../cad-viewer

What gets copied:
  viewer/*              -> target root
  packages/cadjs/*      -> target/packages/cadjs
  packages/cadpy/*      -> target/packages/cadpy

The target checkout must already exist and must be the root of a separate git
repo. Everything in the target root is deleted before copying, except .git.

Options:
  --dry-run  Print what would be overwritten without changing files.
  -h, --help Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      if [ "$#" -gt 0 ]; then
        if [ "$TARGET_SET" -eq 1 ]; then
          echo "Target path was provided more than once." >&2
          usage >&2
          exit 2
        fi
        TARGET_ARG="$1"
        TARGET_SET=1
        shift
      fi
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ "$TARGET_SET" -eq 1 ]; then
        echo "Target path was provided more than once." >&2
        usage >&2
        exit 2
      fi
      TARGET_ARG="$1"
      TARGET_SET=1
      ;;
  esac
  shift
done

if [ "$#" -gt 0 ]; then
  echo "Unexpected extra arguments: $*" >&2
  usage >&2
  exit 2
fi

case "$TARGET_ARG" in
  /*)
    echo "Target must be a relative path; got: $TARGET_ARG" >&2
    exit 2
    ;;
  "")
    echo "Target path must not be empty." >&2
    exit 2
    ;;
esac

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required." >&2
    exit 1
  fi
}

require_path() {
  local path_to_check="$1"
  local label="$2"
  if [ ! -e "$path_to_check" ]; then
    echo "Missing $label: $path_to_check" >&2
    exit 1
  fi
}

require_command git
require_command node
require_command rsync

VIEWER_DIR="$SOURCE_REPO_ROOT/viewer"
CADJS_DIR="$SOURCE_REPO_ROOT/packages/cadjs"
CADPY_DIR="$SOURCE_REPO_ROOT/packages/cadpy"
TARGET_INPUT="$SOURCE_REPO_ROOT/$TARGET_ARG"

require_path "$VIEWER_DIR/package.json" "viewer package"
require_path "$CADJS_DIR/package.json" "cadjs package"
require_path "$CADPY_DIR/pyproject.toml" "cadpy package"

if [ ! -d "$TARGET_INPUT" ]; then
  echo "Target directory does not exist: $TARGET_INPUT" >&2
  echo "Create or clone the standalone cad-viewer repo first." >&2
  exit 1
fi

TARGET_DIR="$(cd "$TARGET_INPUT" && pwd -P)"
SOURCE_REPO_ROOT="$(cd "$SOURCE_REPO_ROOT" && pwd -P)"
TARGET_GIT_ROOT="$(git -C "$TARGET_DIR" rev-parse --show-toplevel 2>/dev/null || true)"

if [ -z "$TARGET_GIT_ROOT" ]; then
  echo "Target is not inside a git repository: $TARGET_DIR" >&2
  exit 1
fi

TARGET_GIT_ROOT="$(cd "$TARGET_GIT_ROOT" && pwd -P)"

if [ "$TARGET_GIT_ROOT" != "$TARGET_DIR" ]; then
  echo "Target must be the root of its own git repo." >&2
  echo "Target:   $TARGET_DIR" >&2
  echo "Git root: $TARGET_GIT_ROOT" >&2
  exit 1
fi

if [ "$TARGET_DIR" = "$SOURCE_REPO_ROOT" ]; then
  echo "Refusing to overwrite the source repo." >&2
  exit 1
fi

if [ "$TARGET_DIR" = "$VIEWER_DIR" ] || [ "$TARGET_DIR" = "$CADJS_DIR" ] || [ "$TARGET_DIR" = "$CADPY_DIR" ]; then
  echo "Refusing to overwrite a source directory: $TARGET_DIR" >&2
  exit 1
fi

RSYNC_EXCLUDES=(
  --exclude node_modules
  --exclude dist
  --exclude dist-verify
  --exclude .vite
  --exclude .next
  --exclude .next-build
  --exclude .next-dev
  --exclude .next-verify
  --exclude .vercel
  --exclude coverage
  --exclude tmp
  --exclude .pytest_cache
  --exclude __pycache__
  --exclude '*.pyc'
  --exclude '*.pyo'
  --exclude .DS_Store
  --include '.env.example'
  --include '.env.*.example'
  --exclude '.env'
  --exclude '.env.*'
)

echo "Source: $SOURCE_REPO_ROOT"
echo "Target: $TARGET_DIR"
echo ""
echo "This will delete everything in the target root except .git, then copy viewer/, packages/cadjs, and packages/cadpy."

if [ "$DRY_RUN" -eq 1 ]; then
  echo ""
  echo "Dry run only. Target entries that would be removed:"
  find "$TARGET_DIR" -mindepth 1 -maxdepth 1 ! -name .git -print | sort
  echo ""
  echo "Dry run only. Copy plan:"
  echo "  $VIEWER_DIR/ -> $TARGET_DIR/"
  echo "  $CADJS_DIR/ -> $TARGET_DIR/packages/cadjs/"
  echo "  $CADPY_DIR/ -> $TARGET_DIR/packages/cadpy/"
  exit 0
fi

find "$TARGET_DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

rsync -a "${RSYNC_EXCLUDES[@]}" "$VIEWER_DIR/" "$TARGET_DIR/"
mkdir -p "$TARGET_DIR/packages"
rsync -a "${RSYNC_EXCLUDES[@]}" "$CADJS_DIR/" "$TARGET_DIR/packages/cadjs/"
rsync -a "${RSYNC_EXCLUDES[@]}" "$CADPY_DIR/" "$TARGET_DIR/packages/cadpy/"

node --input-type=module - "$TARGET_DIR" <<'NODE'
import fs from "node:fs";
import path from "node:path";

const targetRoot = process.argv[2];

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(targetRoot, relativePath), "utf8"));
}

function writeJson(relativePath, value) {
  fs.writeFileSync(path.join(targetRoot, relativePath), `${JSON.stringify(value, null, 2)}\n`);
}

function replaceText(relativePath, replacements) {
  const filePath = path.join(targetRoot, relativePath);
  if (!fs.existsSync(filePath)) {
    return;
  }
  let text = fs.readFileSync(filePath, "utf8");
  for (const [from, to] of replacements) {
    text = text.split(from).join(to);
  }
  fs.writeFileSync(filePath, text);
}

const packageJson = readJson("package.json");
packageJson.dependencies = {
  ...packageJson.dependencies,
  cadjs: "file:./packages/cadjs",
};
if (packageJson.scripts) {
  delete packageJson.scripts["runtime:bundle"];
  delete packageJson.scripts["runtime:check"];
}
writeJson("package.json", packageJson);

const lockPath = path.join(targetRoot, "package-lock.json");
if (fs.existsSync(lockPath)) {
  const lock = readJson("package-lock.json");
  const rootPackage = lock.packages?.[""];
  if (rootPackage?.dependencies) {
    rootPackage.dependencies.cadjs = "file:./packages/cadjs";
  }
  if (lock.packages?.["../packages/cadjs"]) {
    lock.packages["packages/cadjs"] = lock.packages["../packages/cadjs"];
    delete lock.packages["../packages/cadjs"];
  }
  if (lock.packages?.["node_modules/cadjs"]) {
    lock.packages["node_modules/cadjs"].resolved = "packages/cadjs";
  }
  writeJson("package-lock.json", lock);
}

const pathReplacements = [
  ["file:../packages/cadjs", "file:./packages/cadjs"],
  ["../packages/cadjs", "packages/cadjs"],
  ["../packages/cadpy", "packages/cadpy"],
  ["../.venv/bin/python -m pip install -e packages/cadpy", "python -m pip install -e packages/cadpy"],
  ["npm --prefix viewer run upload:blob", "npm run upload:blob"],
  ["npm run build\nnpm run runtime:check", "npm run build"],
  [
    "\nWhen changing Viewer source that feeds the cad-viewer skill runtime, refresh the\ngenerated runtime from the repository root:\n\n```bash\nscripts/bundle/bundle-skill.sh cad-viewer\nscripts/bundle/bundle-skill.sh cad-viewer --check\n```\n",
    "\n",
  ],
  [
    "The generated cad-viewer skill runtime\nbundles `cadpy` under `packages/cadpy` and does not need the repository\nroot.",
    "The standalone checkout keeps `cadpy` under `packages/cadpy` so local\nregeneration can discover it without the source workbench.",
  ],
];
replaceText("README.md", pathReplacements);
replaceText("docs/backend.md", pathReplacements);

const gitignorePath = path.join(targetRoot, ".gitignore");
if (fs.existsSync(gitignorePath)) {
  const gitignore = fs.readFileSync(gitignorePath, "utf8");
  if (!/^\.venv$/mu.test(gitignore)) {
    fs.writeFileSync(gitignorePath, `${gitignore.replace(/\s*$/u, "\n")}.venv\n`);
  }
}
NODE

echo ""
echo "Synced standalone CAD Viewer checkout:"
echo "  $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  cd \"$TARGET_DIR\""
echo "  npm install"
echo "  npm run test"
echo "  npm run build"
