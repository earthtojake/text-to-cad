#!/usr/bin/env bash
# Install this checkout into the Codex app as the development CAD plugin,
# cad@earthtojake-dev: its skills, and a `cadgen mcp` server run by this
# checkout's .venv, serving a copy of this checkout's apps/mcp build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
MARKETPLACE="earthtojake-dev"
PLUGIN_ID="cad@$MARKETPLACE"
DEV_ROOT="$REPO_ROOT/tmp/codex-dev"
PLUGIN_DIR="$DEV_ROOT/plugins/cad"
PYTHON="${CADGEN_PYTHON:-$REPO_ROOT/.venv/bin/python}"
BUILD=1
RESTART=0
UNINSTALL=0

usage() {
  cat <<'EOF'
Usage:
  scripts/install/codex-dev-plugin.sh [--restart] [--no-build]
  scripts/install/codex-dev-plugin.sh --uninstall

Builds apps/mcp, assembles a plugin under tmp/codex-dev from this checkout
(skills copied, server = this checkout's .venv running `cadgen mcp`), and
installs it as cad@earthtojake-dev. Refuses while another CAD plugin is
installed: two copies means every skill twice.

The plugin serves a copy of the built page, taken now, as an installed wheel
serves its own: rebuilding apps/mcp changes nothing until you install again.
A page that changed under a running Codex would change its URI, and Codex
drops the frames already showing it. A running server keeps the code it
started with; --restart quits and reopens the Codex app so every thread gets
this build.

Environment:
  CODEX_CLI      the codex CLI (default: `codex` on PATH, else the one in ChatGPT.app)
  CADGEN_PYTHON  the interpreter that runs the server (default: .venv/bin/python)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart) RESTART=1 ;;
    --no-build) BUILD=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

CODEX="${CODEX_CLI:-}"
if [[ -z "$CODEX" ]]; then
  CODEX="$(command -v codex || true)"
  [[ -n "$CODEX" ]] || CODEX="/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
fi
[[ -x "$CODEX" ]] || { echo "No codex CLI at $CODEX; set CODEX_CLI." >&2; exit 1; }

installed_cad() {
  "$CODEX" plugin list --json | python3 -c '
import json, sys
for plugin in json.load(sys.stdin).get("installed", []):
    if plugin.get("name") == "cad":
        print(plugin["pluginId"])
'
}

if [[ "$UNINSTALL" == 1 ]]; then
  if installed_cad | grep -qx "$PLUGIN_ID"; then "$CODEX" plugin remove "$PLUGIN_ID"; fi
  if "$CODEX" plugin marketplace list | awk '{print $1}' | grep -qx "$MARKETPLACE"; then
    "$CODEX" plugin marketplace remove "$MARKETPLACE"
  fi
  rm -rf "$DEV_ROOT"
  echo "Removed $PLUGIN_ID."
  exit 0
fi

others="$(installed_cad | grep -vx "$PLUGIN_ID" || true)"
if [[ -n "$others" ]]; then
  echo "Another CAD plugin is installed: $others" >&2
  echo "Remove it first (codex plugin remove <id>); two copies means every skill twice." >&2
  exit 1
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

# A version per install, so Codex caches this build rather than reusing the last one.
VERSION="$(tr -d '[:space:]' <"$REPO_ROOT/VERSION")-dev.$(date +%Y%m%d%H%M%S)"
# This install's page. Servers still running an earlier install read their own copy.
APP_DIR="$DEV_ROOT/app/$VERSION"
mkdir -p "$APP_DIR"
cp "$REPO_ROOT/apps/mcp/dist/index.html" "$APP_DIR/index.html"

rm -rf "$PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR/.codex-plugin" "$DEV_ROOT/.agents/plugins"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$REPO_ROOT/skills/" "$PLUGIN_DIR/skills/"
python3 - "$REPO_ROOT" "$DEV_ROOT" "$PLUGIN_DIR" "$MARKETPLACE" "$PYTHON" "$VERSION" "$APP_DIR" <<'EOF'
import json, pathlib, sys
repo, dev, plugin = (pathlib.Path(value) for value in sys.argv[1:4])
marketplace, python, version, app = sys.argv[4:8]
manifest = json.loads((repo / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
manifest["version"] = version
manifest["mcpServers"] = "./codex.mcp.json"
(plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
server = {"mcpServers": {"text_to_cad": {"command": python, "args": ["-m", "cadgen.cli", "mcp"],
                                         "env": {"CADGEN_MCP_APP_DIR": app}, "startup_timeout_sec": 30}}}
(plugin / "codex.mcp.json").write_text(json.dumps(server, indent=2) + "\n", encoding="utf-8")
catalog = {"name": marketplace, "interface": {"displayName": "CAD (this checkout)"}, "plugins": [{
    "name": "cad", "source": {"source": "local", "path": "./plugins/cad"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]}
(dev / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
print(f"assembled {manifest['version']}")
EOF

if ! "$CODEX" plugin marketplace list | awk '{print $1}' | grep -qx "$MARKETPLACE"; then
  "$CODEX" plugin marketplace add "$DEV_ROOT"
fi
"$CODEX" plugin add "$PLUGIN_ID"

if [[ "$RESTART" == 1 ]]; then
  osascript -e 'quit app "ChatGPT"' >/dev/null 2>&1 || true
  for _ in $(seq 1 50); do pgrep -xq ChatGPT || break; sleep 0.2; done
  # No server of an earlier install survives the restart, so neither need its page.
  find "$DEV_ROOT/app" -mindepth 1 -maxdepth 1 ! -name "$VERSION" -exec rm -rf {} +
  open -a ChatGPT
fi
echo "Installed $PLUGIN_ID. New threads run this build$([[ "$RESTART" == 1 ]] || echo " after Codex restarts")."
