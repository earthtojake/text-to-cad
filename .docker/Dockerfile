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
