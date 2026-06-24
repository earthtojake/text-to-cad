#!/bin/bash
set -e

# ── Symlink workaround for Docker volume mount ──
# When the project is mounted at /workspace, the host's empty/missing
# .venv and node_modules shadow the ones we built during docker build.
# We relocate deps to /opt/ and symlink them back at runtime.

# Python venv
if [ -d /opt/venv ] && [ ! -f /workspace/.venv/bin/activate ]; then
    rm -rf /workspace/.venv 2>/dev/null || true
    ln -sf /opt/venv /workspace/.venv
fi

# Viewer node_modules
if [ -d /opt/viewer-node-modules/node_modules ] && [ ! -f /workspace/viewer/node_modules/.package-lock.json ]; then
    rm -rf /workspace/viewer/node_modules 2>/dev/null || true
    mkdir -p /workspace/viewer
    ln -sf /opt/viewer-node-modules/node_modules /workspace/viewer/node_modules
fi

# CAD Viewer packaged runtime — the production viewer bundle lives inside
# the cad-viewer skill directory for the agent:start command
SKILL_VIEWER_DIR="/workspace/skills/cad-viewer/scripts/viewer"
if [ -d /opt/viewer-node-modules/skill-viewer ] && [ -d "$SKILL_VIEWER_DIR" ]; then
    if [ ! -f "$SKILL_VIEWER_DIR/node_modules/.package-lock.json" ]; then
        rm -rf "$SKILL_VIEWER_DIR/node_modules" 2>/dev/null || true
        ln -sf /opt/viewer-node-modules/skill-viewer/node_modules "$SKILL_VIEWER_DIR/node_modules"
    fi
fi

# ── OpenCode config ──
export OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-/home/opencode/.config/opencode}"
mkdir -p "$OPENCODE_CONFIG_DIR"

# Copy default opencode.json if config dir is empty (first start)
if [ ! -f "$OPENCODE_CONFIG_DIR/opencode.json" ]; then
    cp /opt/opencode-defaults/opencode.json "$OPENCODE_CONFIG_DIR/"
fi

# ── Environment ──
export VIRTUAL_ENV=/opt/venv
export PATH="/opt/venv/bin:/home/opencode/.bun/bin:$PATH"
export BUN_INSTALL=/home/opencode/.bun

cd /workspace

# ── Start ttyd with tmux + opencode ──
# tmux runs in background so if the browser tab disconnects and reconnects,
# ttyd reattaches to the same session instead of starting a new opencode process.
exec ttyd -p 8080 -W \
    tmux new-session -s oc -d \; \
    send-keys "cd /workspace && . /opt/venv/bin/activate && exec opencode" Enter
