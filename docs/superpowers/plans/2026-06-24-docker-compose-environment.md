# Docker Compose Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Docker Compose environment with OpenCode pre-configured with text-to-cad skills, CAD Viewer, and full CAD generation (build123d) available via web browser.

**Architecture:** Single Ubuntu 24.04 container with ttyd exposing OpenCode TUI via web (port 8080) and CAD Viewer Vite dev server (port 5173). Python venv at `/opt/venv`, viewer node_modules at `/opt/viewer-node-modules` — both linked via symlinks into the mounted project tree so host source edits don't shadow built deps.

**Tech Stack:** Ubuntu 24.04, Python 3.12, Node.js 22, Bun, OpenCode 1.17.x, build123d, ttyd, Vite 7, React 18, Three.js 0.160

## Global Constraints

- Ubuntu 24.04 (Noble Numbat) as base image — not 22.04, not Alpine
- OpenCode installed via `bun install -g opencode-ai` — not npm
- System Python 3.12 (Ubuntu 24.04 default) — not pyenv, not conda
- No `.env` file required for AI provider — user configures `/connect` inside OpenCode
- ttyd from Ubuntu apt repository — not building from source
- Node.js 22 from NodeSource — matches CI workflows
- The project source is mounted as a Docker volume so user can access generated CAD files from host
- `.venv` and `node_modules/` must survive host volume mount (shadowing) — use symlink trick via entrypoint

---

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `.docker/Dockerfile` | Create | Multi-stage build for the complete environment |
| `.docker/entrypoint.sh` | Create | Runtime setup: symlinks, tmux, ttyd launch |
| `.docker/opencode.json` | Create | OpenCode config pointing at skills/ |
| `docker-compose.yml` | Create | Service definition with ports, volumes, env |
| `.dockerignore` | Create | Exclude unnecessary files from Docker build context |

---

### Task 1: Directory Scaffold + Config Files

**Files:**
- Create: `.docker/opencode.json`
- Create: `.dockerignore`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: nothing
- Produces: OpenCode config consumed by Task 3 (Dockerfile), docker-compose.yml consumed by user at runtime

- [ ] **Step 1: Create `.docker/opencode.json`**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": {
    "paths": [
      "/workspace/skills",
      "/workspace/plugins/cad/skills"
    ]
  }
}
```

This tells OpenCode where to find SKILL.md files for automatic discovery. Both the source `skills/` and the bundled `plugins/cad/skills/` are registered.

- [ ] **Step 2: Create `.dockerignore`**

```
.git
.gitattributes
.gitignore
.lfsconfig
assets/
benchmarks/
node_modules/
.venv/
__pycache__/
*.pyc
.env
.git-lfs/
tmp/
*.gif
```

Prevents large files (LFS assets, benchmarks, giant test GIFs) from bloating the Docker build context.

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  cad-workbench:
    build:
      context: .
      dockerfile: .docker/Dockerfile
    ports:
      - "8080:8080"    # ttyd → OpenCode Web Terminal
      - "5173:5173"    # CAD Viewer Vite Dev Server
    volumes:
      - .:/workspace:cached
      - opencode_data:/home/opencode/.local/share/opencode
    restart: unless-stopped

volumes:
  opencode_data:
```

`:/workspace:cached` — source is mounted so generated models are accessible from host.  
`opencode_data` — persists OpenCode conversation history and provider config across container restarts.

- [ ] **Step 4: Verify files exist**

Run: `ls -la .docker/opencode.json .dockerignore docker-compose.yml`

Expected: three files, all non-empty.

---

### Task 2: Entrypoint Script

**Files:**
- Create: `.docker/entrypoint.sh`

**Interfaces:**
- Consumes: `/opt/venv` and `/opt/viewer-node-modules` (created during Docker build in Task 3)
- Produces: tmux session with OpenCode running, accessible via ttyd on port 8080

- [ ] **Step 1: Create `.docker/entrypoint.sh`**

```bash
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
```

- [ ] **Step 2: Make executable**

Run: `chmod +x .docker/entrypoint.sh`

- [ ] **Step 3: Verify entrypoint syntax**

Run: `bash -n .docker/entrypoint.sh`

Expected: no output (exit code 0).

---

### Task 3: Dockerfile

**Files:**
- Create: `.docker/Dockerfile`

**Interfaces:**
- Consumes: `.docker/opencode.json`, `.docker/entrypoint.sh` (from Tasks 1-2)
- Produces: Docker image with all deps installed at `/opt/venv`, `/opt/viewer-node-modules`, and `/opt/opencode-defaults`

- [ ] **Step 1: Create `.docker/Dockerfile`**

```dockerfile
# =============================================================================
# text-to-cad + OpenCode Docker Environment
# Base: Ubuntu 24.04 (Noble Numbat)
# =============================================================================

FROM ubuntu:24.04 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    python3 python3-dev python3-pip python3-venv \
    git git-lfs \
    build-essential \
    ttyd \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 22 (matches CI) ──
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version | grep -q "^v22"

# ── Bun (for opencode-ai) ──
RUN curl -fsSL https://bun.sh/install | bash
ENV BUN_INSTALL=/root/.bun
ENV PATH=$BUN_INSTALL/bin:$PATH

# ── OpenCode ──
RUN bun install -g opencode-ai && opencode --version

# =============================================================================
# Stage: python-deps — CAD Python packages
# =============================================================================

FROM base AS python-deps
WORKDIR /build

# Copy only dependency manifests for layer caching
COPY packages/cadpy/pyproject.toml packages/cadpy/
COPY packages/cadpy_metadata/pyproject.toml packages/cadpy_metadata/

RUN python3 -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip --quiet && \
    pip install build123d --quiet && \
    pip install -e packages/cadpy --quiet && \
    pip install -e packages/cadpy_metadata --quiet

# Skill-specific Python deps
COPY skills/cad/requirements.txt skills/cad/requirements.txt
COPY skills/dxf/requirements.txt skills/dxf/requirements.txt
COPY skills/urdf/requirements.txt skills/urdf/requirements.txt
COPY skills/srdf/requirements.txt skills/srdf/requirements.txt
COPY skills/sdf/requirements.txt skills/sdf/requirements.txt
COPY skills/cad-viewer/requirements.txt skills/cad-viewer/requirements.txt

RUN . /opt/venv/bin/activate && \
    pip install \
        -r skills/cad/requirements.txt \
        -r skills/dxf/requirements.txt \
        -r skills/urdf/requirements.txt \
        -r skills/srdf/requirements.txt \
        -r skills/sdf/requirements.txt \
        -r skills/cad-viewer/requirements.txt \
        --quiet && \
    pip install ezdxf networkx trimesh --quiet

# Clean pip cache to reduce image size
RUN rm -rf /root/.cache/pip

# =============================================================================
# Stage: node-deps — Viewer and skill JS dependencies
# =============================================================================

FROM base AS node-deps
WORKDIR /build

# Pre-install viewer dependencies at /opt/viewer-node-modules
COPY viewer/package.json viewer/package-lock.json viewer/
COPY packages/cadjs/ packages/cadjs/
COPY packages/implicitjs/ packages/implicitjs/
COPY viewer/packages/ viewer/packages/

RUN mkdir -p /opt/viewer-node-modules && \
    cp -r viewer /opt/viewer-node-modules/ && \
    cd /opt/viewer-node-modules/viewer && \
    npm install --no-audit --no-fund 2>&1

# Also pre-install for the cad-viewer skill's viewer path
COPY skills/cad-viewer/scripts/viewer/package.json skills/cad-viewer/scripts/viewer/ 2>/dev/null || true
RUN if [ -f skills/cad-viewer/scripts/viewer/package.json ]; then \
        mkdir -p /opt/viewer-node-modules/skill-viewer && \
        cp -r skills/cad-viewer/scripts/viewer /opt/viewer-node-modules/skill-viewer/ && \
        cd /opt/viewer-node-modules/skill-viewer/viewer && \
        npm install --no-audit --no-fund 2>&1; \
    fi

# =============================================================================
# Stage: final — assemble runtime
# =============================================================================

FROM base AS final

# Create runtime user
RUN useradd -m -s /bin/bash -u 1000 opencode

# Copy Python venv from python-deps stage
COPY --from=python-deps /opt/venv /opt/venv

# Copy viewer node_modules from node-deps stage
COPY --from=node-deps /opt/viewer-node-modules /opt/viewer-node-modules

# Copy project source
WORKDIR /workspace
COPY . .

# OpenCode defaults config
RUN mkdir -p /opt/opencode-defaults
COPY .docker/opencode.json /opt/opencode-defaults/opencode.json

# Entrypoint
COPY .docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Pre-create opencode data dir with correct ownership
RUN mkdir -p /home/opencode/.config/opencode /home/opencode/.local/share/opencode && \
    chown -R opencode:opencode /home/opencode /opt/venv /opt/viewer-node-modules /opt/opencode-defaults

# Verify key tools
RUN /opt/venv/bin/python -c "import build123d; print('build123d:', build123d.__version__)" && \
    /opt/venv/bin/python -c "import cadpy; print('cadpy: OK')" && \
    node --version && \
    opencode --version

USER opencode
WORKDIR /workspace

EXPOSE 8080 5173
ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 2: Verify Dockerfile syntax**

Run: `docker build --no-cache --target base -t cad-test-base -f .docker/Dockerfile . 2>&1 | tail -5` (quick syntax check, small target only)

Expected: build succeeds, exits with code 0.

---

### Task 4: Build and Smoke Test

**Files:**
- None created — this task runs the build and validates the image

**Interfaces:**
- Consumes: the complete `.docker/Dockerfile`, `.docker/entrypoint.sh`, `.docker/opencode.json`, `docker-compose.yml`

- [ ] **Step 1: Full image build**

Run: `docker compose build 2>&1 | tail -20`

Expected: Build succeeds. Key lines in output:
- "build123d: X.Y.Z" (version printed)
- "cadpy: OK"
- OpenCode version printed

- [ ] **Step 2: Verify expected tools inside image**

Run: `docker compose run --rm cad-workbench /opt/venv/bin/python -c "import build123d; from OCP import BRepPrimAPI; print('OCP OK')"`

Expected: `OCP OK` printed without errors.

- [ ] **Step 3: Verify OpenCode can discover skills**

Run: `docker compose run --rm -e OPENCODE_CONFIG_DIR=/opt/opencode-defaults cad-workbench opencode --version`

Expected: prints OpenCode version (1.17.x).

Note: Full skill discovery validation requires running OpenCode interactively, which is covered in the manual smoke test below.

- [ ] **Step 4: Manual smoke test**

```bash
# Start the service
docker compose up -d

# Check logs
docker compose logs --tail=20

# Open browser to http://localhost:8080
# Expected: ttyd web terminal with OpenCode TUI running
# Run `/connect` inside OpenCode to configure AI provider
# Then try: "List available skills"
# Expected: OpenCode lists 11+ skills including cad, cad-viewer, urdf, etc.
```

- [ ] **Step 5: Verify CAD Viewer access**

After OpenCode is running with a configured provider, ask it to:
"Create a simple 60x40x20mm block and show it in CAD Viewer"

Expected: OpenCode generates the CAD file, starts the viewer (`npm --prefix viewer run agent:start`), and CAD Viewer becomes accessible at `http://localhost:5173`.

- [ ] **Step 6: Verify persistence**

```bash
# Restart the container
docker compose restart

# Open browser to http://localhost:8080
# Expected: OpenCode restores previous session (conversation history intact)
# The AI provider config from `/connect` should still be active
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Ubuntu 24.04 base (Dockerfile: `FROM ubuntu:24.04`)
- ✅ OpenCode via `bun install -g opencode-ai` (Dockerfile: `RUN bun install -g opencode-ai`)
- ✅ ttyd web terminal port 8080 (docker-compose ports + entrypoint)
- ✅ CAD Viewer port 5173 (docker-compose ports)
- ✅ build123d CAD generation (Dockerfile: `pip install build123d`)
- ✅ No .env file (OpenCode `/connect` handles provider config)
- ✅ Skills auto-discovery (opencode.json `skills.paths`)
- ✅ Volume mount for source access (docker-compose volumes)
- ✅ Data persistence (named volume `opencode_data`)
- ✅ Volume mount doesn't shadow deps (entrypoint symlink trick)

**Placeholder scan:** No TBD, TODO, or incomplete sections. All code blocks contain complete, runnable content.

**Type consistency:** Single container, single entrypoint, consistent path references throughout. The `/opt/venv` and `/opt/viewer-node-modules` convention is used consistently in Dockerfile, entrypoint, and verification steps.
