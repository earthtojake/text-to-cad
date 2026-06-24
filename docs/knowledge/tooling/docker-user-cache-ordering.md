# Docker: USER Ordering for Playwright Browser Cache

## Context

Multi-stage Docker build for a text-to-CAD project. The runtime container runs as
a non-root user (`opencode`, UID 1000). Playwright is installed via `npx playwright
install chromium` to pre-download browser binaries for headless testing of the
CAD Viewer (Vite dev server on port 5173).

## Problem

Playwright browser binaries land in `~/.cache/ms-playwright/` under the user
running the install command. If `npx playwright install chromium` runs **before**
`USER opencode` in the Dockerfile, the browsers go to `/root/.cache/ms-playwright/`.
At runtime, the `opencode` user cannot find them — Playwright throws
`ERR_MODULE_NOT_FOUND` or silently fails to launch a browser.

The same issue applies to any tool (npm, pip, cargo) that writes per-user caches
during build: the cache directory is owned by root and inaccessible to the runtime user.

## Solution

Move `USER opencode` **before** the `npx playwright install chromium` line:

```dockerfile
USER opencode

RUN npx playwright install chromium 2>&1
```

This ensures browsers download to `/home/opencode/.cache/ms-playwright/`, which
is accessible when the container runs as `opencode`.

## Why It Works

- Playwright resolves `~/.cache/` from `$HOME` of the current user.
- `USER opencode` sets `$HOME=/home/opencode`.
- The `opencode` user's cache persists in the image layer.
- At runtime, the same user reads the same path — no permission mismatch.

## Side Effects / Tradeoffs

- The `opencode` user must npm/node be accessible (via `npx`) after `USER opencode`.
  In our setup, Node.js is installed globally in the `base` stage, so it's available
  to any user. If the project used a per-user Node install (e.g. nvm), additional
  PATH setup would be needed.
- Pre-installation adds ~300 MB to the image (Chrome + FFmpeg + headless shell).

## Related Files

- `.docker/Dockerfile` — line 149–152: the `USER opencode` / `RUN npx playwright install` ordering
- `.docker/entrypoint.sh` — runtime viewer setup, Vite auto-start

## Tags

`docker` `playwright` `user-cache` `browser-testing` `multi-stage` `container-build`
