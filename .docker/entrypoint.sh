#!/bin/bash
set -e

# ── Symlink workaround for Docker volume mount ──
# When the project is mounted at /workspace, the host's empty/missing
# .venv and node_modules shadow the ones we built during docker build.
# We relocate deps to /opt/ and symlink them back at runtime.

# Python venv — tolerate failure when host volume prevents symlink
if [ -d /opt/venv ] && [ ! -f /workspace/.venv/bin/activate ]; then
    rm -rf /workspace/.venv 2>/dev/null || true
    ln -sf /opt/venv /workspace/.venv 2>/dev/null || true
fi

# Viewer node_modules and packages — set up at non-shadowed path
if [ -d /opt/viewer-source ]; then
    # Fix packages symlinks (the build-time symlink chain is broken after COPY)
    rm -f /opt/viewer-source/packages/cadjs /opt/viewer-source/packages/implicitjs 2>/dev/null || true
    for pkg in cadjs implicitjs; do
        if [ -d /opt/viewer-node-modules/packages/$pkg ]; then
            ln -sf /opt/viewer-node-modules/packages/$pkg /opt/viewer-source/packages/$pkg 2>/dev/null || true
        fi
    done

    # Link pre-installed node_modules
    if [ ! -f /opt/viewer-source/node_modules/.package-lock.json ] && \
       [ -d /opt/viewer-node-modules/viewer/node_modules ]; then
        rm -rf /opt/viewer-source/node_modules 2>/dev/null || true
        ln -sf /opt/viewer-node-modules/viewer/node_modules /opt/viewer-source/node_modules 2>/dev/null || true
    fi

    # Start Vite dev server in background
    if [ -f /opt/viewer-source/node_modules/.bin/vite ]; then
        cd /opt/viewer-source && nohup npx vite --host 0.0.0.0 --port 5173 > /tmp/vite-viewer.log 2>&1 &
    fi
fi

# CAD Viewer packaged runtime (skill directory)
SKILL_VIEWER_DIR="/workspace/skills/cad-viewer/scripts/viewer"
if [ -d /opt/viewer-node-modules/skill-viewer ] && [ -d "$SKILL_VIEWER_DIR" ]; then
    if [ ! -f "$SKILL_VIEWER_DIR/node_modules/.package-lock.json" ]; then
        rm -rf "$SKILL_VIEWER_DIR/node_modules" 2>/dev/null || true
        ln -sf /opt/viewer-node-modules/skill-viewer/node_modules "$SKILL_VIEWER_DIR/node_modules" 2>/dev/null || true
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

# ── Pre-create tmux session with opencode ──
# Create a detached tmux session running opencode so it's ready when the
# first browser tab connects.  Subsequent reconnects (e.g. after a tab
# close) reattach to the same session, preserving the opencode process.
tmux new-session -d -s oc \; \
    send-keys "cd /workspace && . /opt/venv/bin/activate && exec opencode" Enter

# ── Start ttyd → attach to existing tmux session ──
exec ttyd -p 5080 -W tmux attach-session -t oc
