#!/usr/bin/env bash
set -euo pipefail

# The hosted CAD server on this machine, in one command:
#
#   scripts/cloud/dev.sh [--rebuild]
#
# Development sign-in (everyone is `dev`), PGlite and the object store under tmp/cloud,
# and the LOCAL sandbox: the code a build sends runs on this machine, as you, with no
# isolation. --rebuild rebuilds the viewer page (apps/cloud/dist) even when it exists.
# PORT (8787), CLOUD_PYTHON (the checkout's .venv) and every CLOUD_* setting can be
# overridden from the environment; apps/cloud/README.md lists them.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$node_major" -lt 22 ]; then
  echo "dev.sh: the cloud server needs Node 22 or newer (found $(node --version 2>/dev/null || echo none))" >&2
  exit 1
fi

PYTHON="${CLOUD_PYTHON:-$REPO_ROOT/.venv/bin/python}"
if ! "$PYTHON" -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("cadgen") else 1)' 2>/dev/null; then
  echo "dev.sh: $PYTHON cannot import cadgen; install requirements-dev.txt into .venv, or set CLOUD_PYTHON" >&2
  exit 1
fi

if [ "${1:-}" = "--rebuild" ] || [ ! -f apps/cloud/dist/index.html ]; then
  if [ -f apps/cloud/index.html ]; then
    npm run build:cloud
  else
    echo "dev.sh: apps/cloud has no viewer page to build yet; /b/<id> pages answer 503 until it does" >&2
  fi
fi

export NODE_ENV=development
export CLOUD_AUTH=dev
export CLOUD_STORAGE=fs
export CLOUD_SANDBOX=local
export CLOUD_PYTHON="$PYTHON"
export CLOUD_FS_DIR="${CLOUD_FS_DIR:-$REPO_ROOT/tmp/cloud/store}"
export CLOUD_PGLITE_DIR="${CLOUD_PGLITE_DIR:-$REPO_ROOT/tmp/cloud/pglite}"
export PORT="${PORT:-8787}"
export CLOUD_PUBLIC_URL="${CLOUD_PUBLIC_URL:-http://localhost:$PORT}"
mkdir -p "$CLOUD_FS_DIR" "$CLOUD_PGLITE_DIR"

echo "dev.sh: $CLOUD_PUBLIC_URL (MCP at $CLOUD_PUBLIC_URL/mcp; builds run unsandboxed with $PYTHON)" >&2
exec npm run dev -w @text-to-cad/cloud
