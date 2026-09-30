#!/usr/bin/env bash
# Run this checkout's `cadgen mcp` in Claude Desktop as the development CAD server, `cad-dev`:
# an entry in claude_desktop_config.json that starts this checkout's .venv, serving a copy of
# this checkout's apps/mcp build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
NAME="cad-dev"
DEV_ROOT="$REPO_ROOT/tmp/claude-dev"
PYTHON="${CADGEN_PYTHON:-$REPO_ROOT/.venv/bin/python}"
BUILD=1
UNINSTALL=0

case "$(uname -s)" in
  Darwin) DEFAULT_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  MINGW*|MSYS*|CYGWIN*) DEFAULT_CONFIG="${APPDATA:-$HOME/AppData/Roaming}/Claude/claude_desktop_config.json" ;;
  *) DEFAULT_CONFIG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
CONFIG="${CLAUDE_DESKTOP_CONFIG:-$DEFAULT_CONFIG}"

usage() {
  cat <<'EOF'
Usage:
  scripts/install/claude-dev-server.sh [--no-build]
  scripts/install/claude-dev-server.sh --uninstall

Builds apps/mcp and adds a `cad-dev` server to Claude Desktop's config: this
checkout's .venv running `cadgen mcp`, serving a copy of the page taken now (a
page that changed under a running app would change its URI). Every other entry
in the config is kept.

Claude Desktop reads the config when it starts: quit and reopen it, or use
Developer > Reload MCP Configuration (Help > Troubleshooting > Enable Developer
Mode shows that menu). Then ask Claude to show a model with CAD.

Environment:
  CLAUDE_DESKTOP_CONFIG  the config file (default: Claude Desktop's, per platform)
  CADGEN_PYTHON          the interpreter that runs the server (default: .venv/bin/python)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# Rewrite the config with the entry set (or removed), keeping everything else as it was.
write_config() {
  python3 - "$CONFIG" "$NAME" "$@" <<'EOF'
import json, os, sys, tempfile
config_path, name = sys.argv[1], sys.argv[2]
config = {}
if os.path.exists(config_path):
    with open(config_path, encoding="utf-8") as handle:
        text = handle.read().strip()
    config = json.loads(text) if text else {}
servers = config.setdefault("mcpServers", {})
if len(sys.argv) > 3:
    python, app = sys.argv[3], sys.argv[4]
    servers[name] = {"command": python, "args": ["-m", "cadgen.cli", "mcp"], "env": {"CADGEN_MCP_APP_DIR": app}}
else:
    servers.pop(name, None)
os.makedirs(os.path.dirname(config_path), exist_ok=True)
handle, temporary = tempfile.mkstemp(dir=os.path.dirname(config_path), prefix=".claude_desktop_config.")
with os.fdopen(handle, "w", encoding="utf-8") as out:
    json.dump(config, out, indent=2)
    out.write("\n")
os.replace(temporary, config_path)
EOF
}

if [[ "$UNINSTALL" == 1 ]]; then
  write_config
  rm -rf "$DEV_ROOT"
  echo "Removed $NAME from $CONFIG. Restart Claude Desktop to drop it."
  exit 0
fi

"$PYTHON" - "$REPO_ROOT" <<'EOF'
import pathlib, sys
import cadgen.mcp.server  # noqa: F401 - the server must import
root = pathlib.Path(sys.argv[1]).resolve()
if root not in pathlib.Path(cadgen.__file__).resolve().parents:
    sys.exit(f"{sys.executable} imports cadgen from {cadgen.__file__}, not from {root}")
EOF

if [[ "$BUILD" == 1 ]]; then
  (cd "$REPO_ROOT" && npm run build:mcp)
fi
[[ -f "$REPO_ROOT/apps/mcp/dist/index.html" ]] || { echo "apps/mcp is not built; run without --no-build." >&2; exit 1; }

# This install's page; a server still running an earlier one reads its own copy until Claude restarts.
STAMP="$(date +%Y%m%d%H%M%S)"
APP_DIR="$DEV_ROOT/app/$STAMP"
mkdir -p "$APP_DIR"
cp "$REPO_ROOT/apps/mcp/dist/index.html" "$APP_DIR/index.html"
find "$DEV_ROOT/app" -mindepth 1 -maxdepth 1 ! -name "$STAMP" -mtime +1 -exec rm -rf {} +

write_config "$PYTHON" "$APP_DIR"
echo "Added $NAME to $CONFIG. Restart Claude Desktop (or Developer > Reload MCP Configuration) to load it."
