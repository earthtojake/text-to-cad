# =============================================================================
# text-to-cad + OpenCode Docker Environment
# Base: Ubuntu 24.04 (Noble Numbat)
# =============================================================================

FROM ubuntu:24.04 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip \
    python3 python3-dev python3-pip python3-venv \
    git git-lfs \
    build-essential \
    ttyd \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
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

# Copy package source trees for pip install
COPY packages/cadpy/ packages/cadpy/
COPY packages/cadpy_metadata/ packages/cadpy_metadata/

RUN python3 -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip --quiet && \
    pip install build123d --quiet && \
    pip install packages/cadpy --quiet && \
    pip install packages/cadpy_metadata --quiet

# Skill-specific Python deps (cadpy/cadpy_metadata already installed above)
COPY skills/cad/requirements.txt skills/cad/
COPY skills/dxf/requirements.txt skills/dxf/
COPY skills/urdf/requirements.txt skills/urdf/
COPY skills/srdf/requirements.txt skills/srdf/
COPY skills/sdf/requirements.txt skills/sdf/
COPY skills/cad-viewer/requirements.txt skills/cad-viewer/

RUN . /opt/venv/bin/activate && \
    grep -h -v '^--editable' \
        skills/cad/requirements.txt \
        skills/dxf/requirements.txt \
        skills/urdf/requirements.txt \
        skills/srdf/requirements.txt \
        skills/sdf/requirements.txt \
        skills/cad-viewer/requirements.txt \
        > /tmp/skill_reqs.txt && \
    pip install -r /tmp/skill_reqs.txt --quiet && \
    pip install ezdxf networkx trimesh --quiet && \
    rm -rf /root/.cache/pip /tmp/skill_reqs.txt

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
# COPY here (even without a conditional guard) brings the viewer source into
# the build stage for npm install; the RUN cp to /opt preserves the same
# directory structure the entrypoint symlink trick expects.
COPY skills/cad-viewer/scripts/viewer/ /build/skills/cad-viewer/scripts/viewer/
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

# Create runtime user (Ubuntu 24.04 ships an ubuntu user at UID 1000; remove it first)
RUN userdel ubuntu 2>/dev/null; useradd -m -s /bin/bash -u 1000 opencode

# Copy Python venv from python-deps stage
COPY --from=python-deps /opt/venv /opt/venv

# Copy viewer node_modules from node-deps stage
COPY --from=node-deps /opt/viewer-node-modules /opt/viewer-node-modules

# OpenCode defaults config
RUN mkdir -p /opt/opencode-defaults
COPY .docker/opencode.json /opt/opencode-defaults/opencode.json

# Entrypoint
COPY .docker/entrypoint.sh /entrypoint.sh

# Project source
WORKDIR /workspace
COPY . .
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
