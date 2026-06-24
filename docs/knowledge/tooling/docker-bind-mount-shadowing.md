# Docker: Bind Mount Shadows Built-in Source Directories

## Context

A multi-stage Docker image that bakes in project source (e.g. a Vite-based CAD
Viewer at `/workspace/viewer/`) and pre-installs dependencies. At runtime, the
container mounts the host project directory via `-v /host/path:/workspace`.

## Problem

When the host directory is bind-mounted at `/workspace`:
- The host's `/workspace/viewer/` directory **shadows** the one copied into the
  image during `docker build`.
- If the host's `viewer/` is empty, incomplete, or a different version, the
  built-in viewer is inaccessible.
- npm workspace symlinks (`packages/cadjs`, `packages/implicitjs`) are broken
  because they point to paths that exist only at build time.

This is confusing because `ls /workspace/viewer` succeeds but shows stale/wrong
content. There is no error message — the wrong files just serve.

## Solution

1. **At build time**: Copy the viewer source to a non-shadowed path:
   ```dockerfile
   RUN cp -r /workspace/viewer /opt/viewer-source
   ```

2. **At runtime** (in `entrypoint.sh`):
   - Fix package symlinks that broke during COPY:
     ```bash
     for pkg in cadjs implicitjs; do
         ln -sf /opt/viewer-node-modules/packages/$pkg /opt/viewer-source/packages/$pkg
     done
     ```
   - Link pre-installed `node_modules` from the build stage:
     ```bash
     ln -sf /opt/viewer-node-modules/viewer/node_modules /opt/viewer-source/node_modules
     ```
   - Start Vite from the preserved path:
     ```bash
     cd /opt/viewer-source && npx vite --host 0.0.0.0 --port 5173
     ```

## Why It Works

- `/opt/viewer-source` is never bind-mounted by convention — it lives only in
  the image layer.
- The entrypoint runs on every container start, re-linking dependencies that
  would otherwise be stale.
- The symlink approach keeps the viewer code at a path the build-time
  `package.json` expects, avoiding hardcoded path changes.

## Side Effects / Tradeoffs

- Duplicates viewer source in the image (~2× size for that directory).
- Entrypoint complexity: startup must fix symlinks before starting services.
- If the host viewer source is legitimately newer, the entrypoint must be
  bypassed or the image rebuilt.

## Evidence

- Before fix: `curl http://localhost:5173/` returned wrong content (empty
  or broken HTML). Playwright failed to find Vite client scripts.
- After fix: HTTP 200, correct `<title>CAD Viewer</title>`, Vite
  `@react-refresh` and `@vite/client` scripts present, zero page errors.

## Related Files

- `.docker/entrypoint.sh` — the `# Symlink workaround for Docker volume mount` block
- `.docker/Dockerfile` — `RUN cp -r /workspace/viewer /opt/viewer-source`
- `docs/knowledge/tooling/docker-user-cache-ordering.md` — related Docker build-time pitfall

## Tags

`docker` `bind-mount` `volume-shadow` `vite` `viewer` `entrypoint` `symlink`
