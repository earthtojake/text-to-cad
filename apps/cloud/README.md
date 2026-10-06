# Cloud

The hosted CAD server: agents send model code over MCP or REST, a sandbox builds
it with the released cadgen, and the result opens in the same CAD viewer at a
link anyone with the link can open. It is a separate server from `cadgen mcp`,
which runs on the person's own machine.

**PURPOSE** — accept code, run builds, snapshots and inspection scripts in
single-use sandboxes, keep their outputs, and serve each build to the shared
viewer.

**MAY DEPEND ON** — `@text-to-cad/core` and `@text-to-cad/ui` through their
public exports (the viewer page), and its own server dependencies. Never
another app, and never cadgen: the server only ever talks to a sandbox.

**DEPENDED ON BY** — nothing in this repository. The `cad-cloud` skill teaches
agents to use it.

## The laws

1. **The server never runs uploaded code and never imports cadgen.** Every CAD
   operation (a build, a snapshot, an inspection script) runs in a sandbox
   that carries the released cadgen wheel and the runner in `runner/`.
2. **A sandbox is single-use, has no network and holds no credentials.** The
   server writes its inputs and reads its outputs through the provider's file
   API. Whatever a sandbox returns is untrusted data about its own job.
3. **Viewing never wakes compute.** A build's view is its recorded export
   (`cadgen viewer export`), served as a read-only copy of the viewer API at
   `/b/<build>/__cad/*`. Model files come from object storage.
4. **The viewer is `CadViewer`, unchanged.** This app is one more host of the
   viewer host contract (`packages/ui/docs/viewer-host.md`); anything it needs
   from shared UI is a host capability, never a cloud branch.
5. **Every cost has a cap the server enforces.** Per job, per person per day,
   and a global daily budget. Providers rarely stop spending on their own.
6. **A build is immutable.** An edit is a new build: a base build's files plus
   the changes.
7. **Nothing a model sent runs in a viewer's browser.** A sidecar's animation
   module would run on this origin, beside the account pages, so the server
   strips every model script from an export when it ingests it
   (`server/sanitize.ts`), outside the sandbox, whose own steps the model could
   have tampered with. Shared models do not animate until model scripts run in
   an isolated frame.

## Layout

| Path | What |
| --- | --- |
| `server/app.ts` | `createApp(deps)`: every route, over injected `{config, db, store, sandbox, auth, clock}` |
| `server/service.ts` | the one service under REST and MCP: builds, jobs, caps, ingesting sandbox results |
| `server/mcp.ts`, `server/rest.ts` | `/mcp` (stateless Streamable HTTP) and `/v1` |
| `server/auth.ts`, `server/web.ts` | bearer auth, Protected Resource Metadata, OIDC sign-in, `/account` |
| `server/pages.ts` | `/b/<id>[/<path>]` and the compat viewer API mount (`viewerApi.ts`) |
| `server/sandbox/` | the runner protocol and the `local` and `vercel` providers |
| `server/db/schema.sql` | the tables, applied on every start |
| `runner/run.py` | runs one job inside a sandbox (stdlib + cadgen's CLI) |
| `server/node.ts`, `api/index.ts` | the local entry and the Vercel function |

## Run it locally

```bash
scripts/cloud/dev.sh            # http://localhost:8787, MCP at /mcp
```

Development sign-in (`CLOUD_AUTH=dev`), PGlite and the object store under
`tmp/cloud`, and the `local` sandbox: **the code a build sends runs on your
machine, unisolated**. It builds the viewer page into `dist/` when the page
exists; without it `/b/*` answers 503.

Tests: `npm test -w @text-to-cad/cloud` (vitest; the end-to-end test needs a
cadgen Python, `CLOUD_PYTHON` or `.venv`, and is skipped without one),
`npm run typecheck:server -w @text-to-cad/cloud`, and the runner's
`tests/python/apps/cloud`. `node scripts/cloud/prepare-sandbox.mjs` makes the
Vercel Sandbox snapshot (`cadgen==VERSION`, its browser, the runner) and prints
its id; it creates cloud resources, so never in CI.

## Environment

| Variable | Default | |
| --- | --- | --- |
| `CLOUD_PUBLIC_URL` | `http://localhost:$PORT` | origin used in links, resource metadata and token audiences |
| `CLOUD_AUTH` | `oauth` | `dev` signs everyone in as `dev`; refused in production |
| `AUTH_ISSUER`, `AUTH_JWKS_URL` | — | token issuer (OIDC discovery finds the JWKS when unset) |
| `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET`, `AUTH_SCOPES` | — | web sign-in (code + PKCE) |
| `AUTH_AUDIENCE` | — | extra accepted audiences; `<url>/mcp` and `<url>` always are |
| `SESSION_SECRET` | dev only | signs the session cookie, 32+ characters |
| `DATABASE_URL` | — | Postgres (Neon); otherwise PGlite in `CLOUD_PGLITE_DIR`, or memory |
| `CLOUD_STORAGE` | `fs` | `fs` (`CLOUD_FS_DIR`) or `r2` (`R2_ACCOUNT_ID` or `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_PUBLIC_BASE_URL`) |
| `CLOUD_SANDBOX` | `local` | `local` (`CLOUD_PYTHON`; production only with `CLOUD_ALLOW_LOCAL_SANDBOX=1`) or `vercel` (`CLOUD_SANDBOX_SNAPSHOT`; `VERCEL_OIDC_TOKEN` or `VERCEL_TEAM_ID`/`VERCEL_PROJECT_ID`/`VERCEL_TOKEN`) |
| `CLOUD_BUILD_TIMEOUT_S`, `CLOUD_BUILD_VCPUS` | 600, 2 | per build; memory is 2 GB per vCPU |
| `CLOUD_JOB_TIMEOUT_S`, `CLOUD_JOB_VCPUS` | 180, 2 | per snapshot or inspection |
| `CLOUD_MAX_FILES`, `CLOUD_MAX_INPUT_BYTES`, `CLOUD_MAX_OUTPUT_BYTES` | 400, 20 MB, 200 MB | per build |
| `CLOUD_USER_DAILY_VCPU_S` | 3600 | per person per UTC day |
| `CLOUD_DAILY_BUDGET_USD` | 5 | everyone, priced at `CLOUD_CPU_HOUR_USD` 0.128 and `CLOUD_GB_HOUR_USD` 0.0212 |
| `CLOUD_TOOL_WAIT_S` | 40 | how long a tool call or `?wait=` waits |
| `CLOUD_CADGEN_VERSION` | this package's version | the cadgen the sandbox snapshot runs; part of the dedupe key |
| `CRON_SECRET` | — | authorizes `/internal/sweep` (Vercel Cron) |
| `CLOUD_DIST_DIR` | `dist` | the built viewer page |

## Mechanisms

- **Runner protocol.** `request.json` carries the job plus `timeoutSeconds`,
  `vcpus` and `limits`; `result.json` lists every file to collect with its size
  and SHA-256, which the server checks on the way in. Model scripts run
  without `--json`: a non-TTY run still prints cadgen's JSON build events, and
  only the plain failure report names the model's file and line. Inspection
  scripts run with `python -P` (an `inspect.py` would shadow the standard
  library's).
- **Builds.** `entry` is optional: without one nothing runs and the CAD files
  sent are published. Outputs are the files the scripts created or changed with
  a CAD, sidecar, mesh, drawing or image suffix (others are dropped and named);
  symlinks and `tmp/` never count. Every viewable file is exported, inputs
  included. The link opens the STEP named for the first entry, else the
  shallowest STEP, else the first viewable file. An identical request (files,
  entry, pythonpath, cadgen version) returns the earlier build unless it failed
  for a reason other than its code.
- **Caps.** A job reserves its worst case (vCPUs × timeout, and its price)
  with conditional updates before it starts, and settles vCPUs × sandbox wall
  time afterwards. A person's daily allowance shortens a job's timeout to what
  is left and refuses it below `CLOUD_MIN_JOB_S`. One build and one
  snapshot/inspection at a time per person is a unique index, not a check.
  The sweeper fails jobs past their timeout plus `CLOUD_STALE_GRACE_S` and
  charges their whole reservation; a server on PGlite fails, as it starts,
  whatever an earlier process left running. Request bodies are capped (32 MB on
  `/mcp` and `/v1`) before anything reads them.
- **Access.** Builds are public by id (`/b/<id>`, `GET /v1/builds/<id>` and its
  files); jobs, lists and keys belong to their owner. MCP discovery works signed
  out and `tools/call` answers 401 with the metadata URL. API keys cannot create
  keys.
- **Vercel.** `/` goes to the function before static files; builds continue in
  `waitUntil` within `maxDuration` 800 s. The platform's 4.5 MB request limit
  caps inline files there until uploads go straight to storage.
