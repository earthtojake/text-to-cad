#!/bin/bash
set -e

RUNTIME_UID="${LOCAL_UID:-1000}"
RUNTIME_GID="${LOCAL_GID:-1000}"

if [ "${1:-}" = "--as-opencode" ]; then
    shift
fi

if [ "$(id -u)" -eq 0 ]; then
    current_uid="$(id -u opencode)"
    current_gid="$(id -g opencode)"

    if getent group "$RUNTIME_GID" >/dev/null; then
        target_group="$(getent group "$RUNTIME_GID" | cut -d: -f1)"
    else
        groupmod -g "$RUNTIME_GID" opencode
        target_group="opencode"
    fi

    if [ "$target_group" != "$(id -gn opencode)" ]; then
        usermod -g "$target_group" opencode
    fi

    if existing_user="$(getent passwd "$RUNTIME_UID" | cut -d: -f1 2>/dev/null)"; then
        if [ -n "$existing_user" ] && [ "$existing_user" != "opencode" ]; then
            echo "LOCAL_UID $RUNTIME_UID is already owned by user '$existing_user'; set LOCAL_UID/LOCAL_GID explicitly." >&2
            exit 1
        fi
    fi

    if [ "$RUNTIME_UID" != "$current_uid" ]; then
        usermod -u "$RUNTIME_UID" opencode
    fi

    mkdir -p /home/opencode/.config/opencode /home/opencode/.local/share/opencode

    # Materialize the project source from the image-internal seed into the
    # /workspace named volume on first boot.  Subsequent restarts skip the
    # copy so generated files (models/, .venv, etc.) survive.
    if [ -d /opt/workspace-seed ] && [ -z "$(ls -A /workspace 2>/dev/null)" ]; then
        cp -a /opt/workspace-seed/. /workspace/
    fi

    mkdir -p /workspace/models
    chown -R "$RUNTIME_UID:$RUNTIME_GID" /workspace

    exec su -s /bin/bash opencode -c 'exec /entrypoint.sh --as-opencode'
fi

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
fi

# Prefer running Vite from /workspace/viewer (named volume) so HMR sees
# source edits; fall back to /opt/viewer-source only if the volume lacks it.
if [ -d /workspace/viewer ] && [ -f /workspace/viewer/node_modules/.bin/vite ]; then
    cd /workspace/viewer && nohup npx vite --host 0.0.0.0 --port 5173 > /tmp/vite-viewer.log 2>&1 &
elif [ -f /opt/viewer-source/node_modules/.bin/vite ]; then
    cd /opt/viewer-source && nohup npx vite --host 0.0.0.0 --port 5173 > /tmp/vite-viewer.log 2>&1 &
fi

# CAD Viewer packaged runtime (skill directory)
SKILL_VIEWER_DIR="/workspace/skills/cad-viewer/scripts/viewer"
if [ -d /opt/viewer-node-modules/skill-viewer ] && [ -d "$SKILL_VIEWER_DIR" ]; then
    if [ ! -f "$SKILL_VIEWER_DIR/node_modules/.package-lock.json" ]; then
        rm -rf "$SKILL_VIEWER_DIR/node_modules" 2>/dev/null || true
        ln -sf /opt/viewer-node-modules/skill-viewer/node_modules "$SKILL_VIEWER_DIR/node_modules" 2>/dev/null || true
    fi
fi

# Repair the seeded /workspace/viewer symlinks (the build-time seed carries
# the source tree with placeholder symlinks to image-internal paths; re-link
# node_modules and packages to the real cache so Vite resolves dependencies).
if [ -d /workspace/viewer ] && [ -d /opt/viewer-node-modules/viewer/node_modules ]; then
    rm -f /workspace/viewer/node_modules 2>/dev/null || true
    ln -sf /opt/viewer-node-modules/viewer/node_modules /workspace/viewer/node_modules 2>/dev/null || true
    for pkg in cadjs implicitjs; do
        rm -f "/workspace/viewer/packages/$pkg" 2>/dev/null || true
        if [ -d "/opt/viewer-node-modules/packages/$pkg" ]; then
            ln -sf "/opt/viewer-node-modules/packages/$pkg" "/workspace/viewer/packages/$pkg" 2>/dev/null || true
        fi
    done
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
