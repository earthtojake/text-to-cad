#!/usr/bin/env bash
# Verifies the cad-workbench compose stack on this branch.
#
# What this script checks:
#   1. compose config resolves with no bind mount on /workspace
#   2. the cad-workbench container is running
#   3. /workspace is a named volume (no host-bind overlay)
#   4. /workspace contains the seeded project tree
#   5. /workspace/viewer has its node_modules and packages symlinks
#   6. /workspace/models exists and is writable by the opencode user
#   7. the opencode user can write to /workspace and /workspace/models
#   8. ttyd (5080) and viewer (5173) respond inside the container
#   9. Vite dev server cwd is /workspace/viewer
#  10. the viewer serves ?dir=/workspace/models with HTTP 200
#
# Usage:
#   tmp/compose-verify.sh                  # uses defaults
#   OPENCODE_TTYD_PORT=5180 \
#   VIEWER_HOST_PORT=8081 \
#   tmp/compose-verify.sh                  # override published ports
#
# This script is intentionally read-only against compose state; it does not
# bring services up or down.  Pair it with `docker compose up -d` upstream.

set -euo pipefail

CONTAINER="${CONTAINER:-gentle-salamander-cad-workbench-1}"
SERVICE="${SERVICE:-cad-workbench}"

OPENCODE_TTYD_PORT="${OPENCODE_TTYD_PORT:-5080}"
VIEWER_HOST_PORT="${VIEWER_HOST_PORT:-5173}"

pass=0
fail=0
log() { printf '%s\n' "$*"; }
ok() { log "  [ok] $*"; pass=$((pass+1)); }
bad() { log "  [FAIL] $*"; fail=$((fail+1)); }
section() { log; log "== $* =="; }

section "1. compose config"
config_yaml="$(docker compose config 2>/dev/null || true)"
if [ -z "$config_yaml" ]; then
    bad "docker compose config returned no output"
    exit 1
fi
if printf '%s\n' "$config_yaml" | grep -Eq 'source:\s*opencode_workspace\b'; then
    ok "opencode_workspace volume declared and bound to /workspace"
else
    bad "opencode_workspace volume not bound to /workspace"
fi
if printf '%s\n' "$config_yaml" | grep -Eq 'source:\s*/workspace\b'; then
    bad "compose still binds a host /workspace path"
else
    ok "no host bind on /workspace"
fi

section "2. container status"
status="$(docker compose ps --format '{{.State}}' "$SERVICE" 2>/dev/null || true)"
if [ "$status" = "running" ]; then
    ok "service '$SERVICE' is running"
else
    bad "service '$SERVICE' state: '$status'"
    log "  hint: run 'OPENCODE_TTYD_PORT=$OPENCODE_TTYD_PORT VIEWER_HOST_PORT=$VIEWER_HOST_PORT docker compose up -d'"
    exit 1
fi

section "3. /workspace mount is a named volume"
mount_line="$(docker compose exec -T "$SERVICE" sh -lc "grep -E ' /workspace( |$|\$)' /proc/self/mountinfo | head -1" 2>/dev/null || true)"
if [ -z "$mount_line" ]; then
    bad "could not read /workspace mount info"
else
    volume_path="$(printf '%s\n' "$mount_line" | sed -nE 's#.* (/var/lib/docker/volumes/[^ ]*) /workspace .*#\1#p')"
    case "$mount_line" in
        *"/var/lib/docker/volumes/"*"opencode_workspace"*)
            ok "/workspace mounted from named volume: ${volume_path:-opencode_workspace}" ;;
        *"/var/lib/docker/volumes/"*)
            bad "/workspace mounted from a docker volume, but not opencode_workspace: ${volume_path:-unknown}" ;;
        *)
            bad "/workspace not mounted from a docker volume" ;;
    esac
fi

section "4. /workspace seeded tree"
missing=""
for entry in AGENTS.md docker-compose.yml models viewer skills docs packages; do
    if ! docker compose exec -T "$SERVICE" sh -lc "[ -e /workspace/$entry ]" >/dev/null 2>&1; then
        missing="$missing $entry"
    fi
done
if [ -z "$missing" ]; then
    ok "expected project entries present in /workspace"
else
    bad "missing entries under /workspace:$missing"
fi

section "5. /workspace/viewer symlinks"
for target in node_modules packages/cadjs packages/implicitjs; do
    link="$(docker compose exec -T "$SERVICE" sh -lc "readlink /workspace/viewer/$target" 2>/dev/null || true)"
    if [ -n "$link" ] && [ "$link" != "/dev/null" ]; then
        ok "viewer/$target -> $link"
    else
        bad "viewer/$target not a symlink"
    fi
done

section "6. /workspace/models exists and is writable by opencode"
if docker compose exec -T "$SERVICE" sh -lc 'test -d /workspace/models' >/dev/null 2>&1; then
    ok "/workspace/models exists"
else
    bad "/workspace/models missing"
fi
if docker compose exec -T "$SERVICE" sh -lc 'su -s /bin/bash opencode -c "test -w /workspace/models"' >/dev/null 2>&1; then
    ok "opencode user can write to /workspace/models"
else
    bad "opencode user cannot write to /workspace/models"
fi

section "7. opencode write test (creates and removes a file)"
write_ok="$(docker compose exec -T "$SERVICE" sh -lc 'su -s /bin/bash opencode -c "f=/workspace/.compose-verify-write; touch \$f && rm \$f && echo ok"' 2>/dev/null || true)"
if [ "$write_ok" = "ok" ]; then
    ok "opencode wrote and removed /workspace/.compose-verify-write"
else
    bad "opencode write test failed: $write_ok"
fi

section "8. ttyd and viewer listening inside container"
if docker compose exec -T "$SERVICE" sh -lc 'python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect((\"127.0.0.1\", 5080)); s.close(); print(\"ok\")"' >/dev/null 2>&1; then
    ok "container 127.0.0.1:5080 reachable"
else
    bad "container 127.0.0.1:5080 not reachable"
fi
if docker compose exec -T "$SERVICE" sh -lc 'python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect((\"127.0.0.1\", 5173)); s.close(); print(\"ok\")"' >/dev/null 2>&1; then
    ok "container 127.0.0.1:5173 reachable"
else
    bad "container 127.0.0.1:5173 not reachable"
fi

section "9. Vite dev server cwd is /workspace/viewer"
vite_bin="$(docker compose exec -T "$SERVICE" sh -lc 'pgrep -af "node.*\\.bin/vite" | head -1' 2>/dev/null || true)"
case "$vite_bin" in
    *"/workspace/viewer/node_modules/.bin/vite"*) ok "vite running from /workspace/viewer";;
    *) bad "vite binary path unexpected: $vite_bin";;
esac

section "10. viewer HTTP for ?dir=/workspace/models"
status="$(docker compose exec -T "$SERVICE" sh -lc 'python3 -c "import urllib.request; r=urllib.request.urlopen(\"http://127.0.0.1:5173/?dir=/workspace/models\", timeout=5); print(r.status)"' 2>/dev/null || true)"
if [ "$status" = "200" ]; then
    ok "viewer /?dir=/workspace/models returned 200"
else
    bad "viewer /?dir=/workspace/models returned: $status"
fi

section "summary"
log "passed: $pass"
log "failed: $fail"
if [ "$fail" -gt 0 ]; then
    exit 1
fi
log "compose-verify: all checks passed"
