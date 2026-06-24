# Docker Compose Workbench Environment

## Context

The `text-to-cad` workbench is a Docker Compose stack that runs an
OpenCode Web Terminal (`ttyd` on container port `5080`) and the CAD
Viewer Vite dev server (container port `5173`) inside a single
`cad-workbench` container. The container also hosts the project source
itself, since OpenCode reads and writes CAD generation artifacts
(`models/`, `*.step`, `*.urdf`, etc.) under `/workspace`.

This entry documents the runtime contract for that stack as shipped on
the `feat/docker-compose-environment` branch — the bind mount, named
volumes, image-internal seed, and runtime UID/port overrides.

## Problem

Two patterns that the earlier bind-mount layout made fragile:

1. **Host overlay breaks the workspace tree.**  
   When the host project is bind-mounted at `/workspace`, the host's
   `viewer/`, `models/`, or `scripts/` shadows the image-internal copy.
   In particular, an LFS-not-yet-hydrated or worktree-incomplete host
   shows the container a partial tree (e.g. an empty `models/` or a
   stray `desk.py` left over from a previous AI run). The container
   then disagrees with the host repo, and the viewer catalog does not
   match what the user sees on disk.

2. **`/workspace` ownership is unpredictable.**  
   The container runs as `opencode` (UID `1000` by default) but the
   host worktree is owned by the host UID. Bind mounts with `:cached`
   only show the host's mode bits; the runtime user could not create
   new files under `/workspace` without a manual `chown` or a matching
   host UID. AI-generated files then silently fail with `EACCES`.

## Solution

Switch the `/workspace` mount from a host bind to a named volume
populated by an image-internal seed on first boot:

```yaml
# docker-compose.yml (relevant lines)
services:
  cad-workbench:
    user: "0:0"
    environment:
      LOCAL_UID: "${LOCAL_UID:-1000}"
      LOCAL_GID: "${LOCAL_GID:-1000}"
    volumes:
      - opencode_workspace:/workspace
      - opencode_data:/home/opencode/.local/share/opencode

volumes:
  opencode_workspace:
  opencode_data:
```

The Dockerfile copies the project source into an image-internal path
(`/opt/workspace-seed`) and the entrypoint materializes it into the
named volume on first boot:

```dockerfile
# .docker/Dockerfile (relevant lines)
WORKDIR /opt/workspace-seed
COPY . .
RUN mkdir -p /opt/viewer-source && \
    cp -r /opt/workspace-seed/viewer /opt/viewer-source
```

```bash
# .docker/entrypoint.sh (relevant lines, root stage)
if [ -d /opt/workspace-seed ] && [ -z "$(ls -A /workspace 2>/dev/null)" ]; then
    cp -a /opt/workspace-seed/. /workspace/
fi
mkdir -p /workspace/models
chown -R "$RUNTIME_UID:$RUNTIME_GID" /workspace
exec su -s /bin/bash opencode -c 'exec /entrypoint.sh --as-opencode'
```

The host-port side is also parameterized to avoid collisions when
multiple stacks share a machine:

```yaml
ports:
  - "${OPENCODE_TTYD_PORT:-5080}:5080"
  - "${VIEWER_HOST_PORT:-5173}:5173"
```

`scripts/dev/compose-verify.sh` asserts all of the above at runtime.

## Why It Works

- **Image-internal seed, volume-resident runtime.**  
  `/opt/workspace-seed` is only readable at runtime via the entrypoint
  copy, so the container never reads source from the host. Subsequent
  restarts see a non-empty `/workspace` and skip the copy, so generated
  files (CAD artifacts, `.venv`, `node_modules` symlinks) survive
  across restarts.

- **Root-at-startup, drop-priv-after.**  
  The `user: 0:0` in compose plus the `LOCAL_UID`/`LOCAL_GID` re-map in
  the entrypoint lets the container `chown /workspace` and `usermod
  opencode` before handing off to the non-root `opencode` user that
  actually runs the long-lived processes. This is necessary because
  Docker named volumes always start owned by `root` on first mount.

- **Viewer serves from `/workspace/viewer`.**  
  The Vite dev server is launched from `/workspace/viewer` (with
  `node_modules` and `packages/{cadjs,implicitjs}` symlinked to
  `/opt/viewer-node-modules/...`). The seeded symlinks from the build
  time are re-linked in the entrypoint, so HMR sees source edits and
  the viewer URL is `?dir=/workspace/models`.

- **Port override, not host bind.**  
  Overriding `OPENCODE_TTYD_PORT` and `VIEWER_HOST_PORT` at `up` time is
  enough to avoid `5080` / `5173` collisions; no bind mount means no
  `:ro` vs `:rw` consistency confusion.

## Side Effects / Tradeoffs

- **No live host editing.**  
  Editing source on the host does not propagate to the running
  container; developers must `docker compose down && docker compose up
  --build -d` to refresh. This is the explicit trade for avoiding the
  host overlay problem.

- **First-boot copy is the source of truth.**  
  If the volume is non-empty the entrypoint skips the seed copy, so a
  stale `opencode_workspace` volume can mask a freshly-built image. Run
  `docker compose down -v` when re-seeding is intended.

- **Playwright cache is not pre-installed in the image.**  
  Earlier iterations baked `npx playwright install chromium` into the
  Dockerfile. That was removed because the development environment
  already provides the cache; relying on the image for it doubled the
  build time without changing the runtime contract. If a fresh CI
  environment lacks the cache, install it via the host before bringing
  the container up.

- **`opencode_workspace` is not LFS-aware.**  
  LFS pointer files in the seed copy as plain text. Hydrate
  `git lfs pull` on the host after `git lfs checkout`, or run LFS-aware
  tooling inside the container, before depending on LFS-backed
  artifacts.

## Evidence

Validated on `feat/docker-compose-environment` with
`scripts/dev/compose-verify.sh` (15 / 15 checks pass):

```
== 1. compose config ==
  [ok] opencode_workspace volume declared and bound to /workspace
  [ok] no host bind on /workspace

== 2. container status ==
  [ok] service 'cad-workbench' is running

== 3. /workspace mount is a named volume ==
  [ok] /workspace mounted from named volume: /var/lib/docker/volumes/gentle-salamander_opencode_workspace/_data

== 4. /workspace seeded tree ==
  [ok] expected project entries present in /workspace

== 5. /workspace/viewer symlinks ==
  [ok] viewer/node_modules -> /opt/viewer-node-modules/viewer/node_modules
  [ok] viewer/packages/cadjs -> /opt/viewer-node-modules/packages/cadjs
  [ok] viewer/packages/implicitjs -> /opt/viewer-node-modules/packages/implicitjs

== 6. /workspace/models exists and is writable by opencode ==
  [ok] /workspace/models exists
  [ok] opencode user can write to /workspace/models

== 7. opencode write test (creates and removes a file) ==
  [ok] opencode wrote and removed /workspace/.compose-verify-write

== 8. ttyd and viewer listening inside container ==
  [ok] container 127.0.0.1:5080 reachable
  [ok] container 127.0.0.1:5173 reachable

== 9. Vite dev server cwd is /workspace/viewer ==
  [ok] vite running from /workspace/viewer

== 10. viewer HTTP for ?dir=/workspace/models ==
  [ok] viewer /?dir=/workspace/models returned 200
```

Host-side reachability was confirmed manually at
`http://<host>:8081/?dir=/workspace/models` and
`http://<host>:5180/`.

## Related Files

- `docker-compose.yml`
- `.docker/Dockerfile`
- `.docker/entrypoint.sh`
- `scripts/dev/compose-verify.sh`
- `.opencode/skills/cad-workbench.md`
- `docs/knowledge/tooling/docker-bind-mount-shadowing.md` (predecessor lesson)
- `docs/knowledge/tooling/docker-user-cache-ordering.md` (predecessor lesson)

## Tags

- docker
- compose
- named-volume
- opencode
- viewer
- ttyd
- workbench
