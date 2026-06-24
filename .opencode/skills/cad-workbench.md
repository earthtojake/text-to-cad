---
name: cad-workbench
description: Verify the cad-workbench docker compose stack is running with the expected named-volume layout, writable AI output paths, and live ttyd / viewer HTTP endpoints.
---

# cad-workbench skill

Use this skill to run the workbench's compose stack smoke test from inside an
agent session. It wraps the durable `scripts/dev/compose-verify.sh` script;
do not duplicate the checks here.

## Triggers

- "verify compose"
- "check cad-workbench"
- "smoke test the workbench"
- "is docker compose up"
- "驗證 docker compose"
- "檢查 cad-workbench"

---

## When To Use

- after `docker compose up -d` / `--build`
- after any change to `docker-compose.yml`, `.docker/Dockerfile`, or
  `.docker/entrypoint.sh`
- when the user reports that AI-generated CAD files do not appear in the
  viewer, or that the ttyd terminal is unreachable
- before opening a PR that touches the workbench runtime

Do **not** use for:

- ad-hoc container shell commands (use `docker compose exec` directly)
- full integration tests of viewer or skills (use the test suites in
  `scripts/test/`)

---

## Required Inputs

- (optional) `OPENCODE_TTYD_PORT` and `VIEWER_HOST_PORT` if the host ports
  differ from the compose defaults (`5080` / `5173`)

---

## Procedure

1. Run the verifier:
   ```bash
   OPENCODE_TTYD_PORT="${OPENCODE_TTYD_PORT:-5180}" \
   VIEWER_HOST_PORT="${VIEWER_HOST_PORT:-8081}" \
   scripts/dev/compose-verify.sh
   ```
2. If any check fails, read the `compose-verify` output and follow the
   hints it prints (e.g. the `container status` section tells the operator
   to bring services up).
3. If the failure is on `compose config` or `/workspace` mount, treat it as
   a `docker-compose.yml` regression and revert / fix that file before
   continuing.

---

## What It Checks (Summary)

The script asserts 10 sections / 15 checks:

1. `docker compose config` declares `opencode_workspace` and has no host
   bind on `/workspace`
2. the `cad-workbench` service is `running`
3. `/workspace` is mounted from the `opencode_workspace` named volume
4. `/workspace` contains the seeded project tree
5. `/workspace/viewer/{node_modules,packages/cadjs,packages/implicitjs}` are
   symlinks to `/opt/viewer-node-modules/...`
6. `/workspace/models` exists and is writable by the `opencode` user
7. the `opencode` user can write and remove a test file under `/workspace`
8. containers `127.0.0.1:5080` (ttyd) and `127.0.0.1:5173` (viewer) are
   reachable
9. Vite dev server is running from `/workspace/viewer`
10. `http://127.0.0.1:5173/?dir=/workspace/models` returns `200`

The script is read-only against compose state; it does not bring services up
or down.

---

## Related Files

- `docker-compose.yml`
- `.docker/Dockerfile`
- `.docker/entrypoint.sh`
- `scripts/dev/compose-verify.sh`
- `docs/knowledge/tooling/docker-compose-environment.md`
