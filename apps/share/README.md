# Share

`cad.fun`: where a shared model lives. `cad share` uploads a document's view bundle, packed into
one archive and encrypted, and anyone with the link opens it in the hosted viewer, with no sign-in.
A share expires 7 days after its last upload. The service is a Cloudflare Worker of its own
(`cad-share`) over an R2 bucket (`cad-shares`), serving the viewer's built client as its static
assets.

**PURPOSE** — keep a share, encrypted, for 7 days; hand its bytes to whoever has its link; and serve
the page that opens it. Its routes, statuses, headers and the archive's format are a contract with
every released `cad share` and with the page: they never break.

**MAY DEPEND ON** — Cloudflare Workers' runtime (the web-standard `Request`, `Response` and
`crypto.subtle`), its R2, static assets and rate limiting bindings, and Node's standard library for
the local runner and the tests: no npm dependencies, so there is nothing to install. It is not one
of the root npm workspaces and has no lockfile. Its static assets are `apps/web`'s build output,
copied in before a deploy; it imports nothing of any app or package.

**DEPENDED ON BY** — nothing in the repo imports it. `cad share` (`packages/cad`) reaches it over
HTTPS (`CAD_SHARE_URL` points it at another origin), and the viewer's share mode (`apps/web`,
`packages/core`) is the page it serves at `/<id>`.

## Build, run, deploy

```
src/worker.mjs  # the Worker: the whole service, a fetch(request, env, ctx) handler
src/local.mjs   # the platform, locally: stand-ins for R2, the static assets, the limiter, the routing
serve.mjs       # the local runner: the real Worker over Node's http
build.mjs       # copies apps/web's build into viewer/, the Worker's static assets (ignored)
wrangler.jsonc  # the Worker, its bucket, its limiter, its assets, its two variables
```

```bash
npm --prefix apps/share test          # or scripts/test/test-share.sh, which CI runs (static)
npm run build:web                     # at the root, after npm ci: the viewer, into apps/web/dist
npm --prefix apps/share run build     # apps/web/dist -> apps/share/viewer
node apps/share/serve.mjs --port 8787 --assets apps/share/viewer [--store tmp/share]
```

`serve.mjs` serves `src/worker.mjs` itself, over stand-ins that do what the Worker asks of
Cloudflare: an R2 bucket in memory (or files under `--store`) whose `put` honours `onlyIf`, an
assets binding over the folder given that answers exactly what `wrangler.jsonc`'s
`html_handling: "none"` answers, the asset-first routing and `run_worker_first` read from
`wrangler.jsonc`, `CF-Connecting-IP` set from the socket, and a limiter that allows everything.
`--port 0` takes any free port. When it is ready it prints its origin, and nothing else, on one
line (`http://127.0.0.1:8787`); point `CAD_SHARE_URL` there. It stops on SIGINT or SIGTERM.

Deployment is the `Deploy Share` workflow only (`.github/workflows/deploy-share.yml`), on
dispatch: it runs the tests, builds the viewer, copies it in, deploys with Wrangler (pinned, through
`npx`), and then asks `SHARE_ORIGIN` that `/` redirects and an unknown share is `404`.

## The API

Every answer that is not a share's bytes is JSON. A refusal is `{"error": "...", "hint": "..."}`
with its status: `error` a fixed word for a program, `hint` a sentence for a person.

| Value | Form |
| --- | --- |
| share id | 16 random bytes, base64url without padding: 22 characters, `^[A-Za-z0-9_-]{22}$` |
| key | 32 random bytes, base64url, 43 characters: an AES-256-GCM key |
| write secret | 32 random bytes, base64url, 43 characters: upload again |
| delete secret | 32 random bytes, base64url, 43 characters: delete |

The command makes all four with a cryptographic generator. The service keeps each secret only as
the lowercase hex SHA-256 of its text, the 43 characters as they travel; it never keeps the key.

**`PUT /v1/shares/<id>`**, upload or upload again: `Authorization: Bearer <write secret>`,
`Cad-Share-Key: <key>`, `Cad-Delete-Hash: <hex SHA-256 of the delete secret>`, a `Content-Length`,
and the archive as the body.

| Status | `error` | When |
| --- | --- | --- |
| `201` | | Made: `{"id", "expires", "bytes"}`, `expires` ISO 8601, `bytes` the size stored |
| `200` | | Replaced, the same body: the 7 days start again |
| `400` | `bad_id`, `bad_key`, `bad_delete_hash`, `not_gzip` | The id, the key or the hash malformed; a body that does not start with gzip's `1f 8b` |
| `401` | `unauthorized` | No `Authorization: Bearer` with a 43-character secret |
| `403` | `forbidden` | A share with this id exists, made under another write secret |
| `409` | `conflict` | Another upload to the id changed it three times while this one was judged; try again |
| `411` | `length_required` | No `Content-Length` |
| `413` | `too_large` | Over `MAX_SHARE_BYTES` (25 MiB), by its length or by its body |
| `429` | `rate_limited` | More uploads and deletes from this address than the limit (`Retry-After: 60`) |

An upload is encrypted with AES-256-GCM under its key and a fresh random 12-byte IV, and stored as
`IV || ciphertext-and-tag` under the id, with the format (`cad-share/1`), the two hashes and the
expiry (now plus `EXPIRY_DAYS`, 7) beside it as R2 custom metadata. A create is a put only if no
object has the id, and a replace a put only if the object is still the one judged, so one client's
upload never overwrites a share another made at the same moment: the later is judged against the
earlier, and refused unless it holds the same write secret. An expired share is no share, so its id
can be made again.

**`GET /v1/shares/<id>`** (and `HEAD`): the stored bytes, `Content-Type: application/octet-stream`,
`Cache-Control: no-store`, `Cad-Share-Expires: <ISO 8601>`. `404` (`not_found`) for an id with no
share, whether it never existed, expired or was deleted: a share read past its expiry is deleted
then. `400` for a malformed id.

**`DELETE /v1/shares/<id>`**: `Authorization: Bearer <delete secret or write secret>`. `204` when
deleted, `404` for no share, `403` for a secret that matches neither hash, `401` for none, `429` past
the rate limit.

Another method on the route is `405` with `Allow`; any other `/v1` path is `404`.

## The archive (`cad-share/1`)

The view bundle's folder ([view-bundle.md](../../packages/cad/src/cad_server/engine/docs/view-bundle.md))
as a gzip-compressed POSIX ustar archive: every regular file by its path relative to the bundle's
root, `/` separated, `manifest.json` among them; no folders, links or other entries, no absolute
path, no `..`, no duplicate; sorted by path, every entry with mtime 0, mode 0644, uid and gid 0 and
empty user and group names; gzip with mtime 0, so the same bundle makes the same bytes. A path that
does not fit a ustar header (name 100 bytes, prefix 155) is refused by the command. `thumbnail.png`
is left out (it may show an earlier version of the document). The service checks only gzip's magic
bytes: it cannot read what it stores.

## The pages

- `GET /` redirects (`302`) to `https://www.texttocad.dev`.
- `GET /<id>`, a path that is one share id: the viewer's `index.html`, whatever the fragment. The
  page reads `#key=<key>` to fetch, decrypt, gunzip and open the bundle, and `#delete=<secret>` to
  offer the delete. A browser never sends a fragment to a server.
- Any other path: the viewer's own files (scripts, styles, images), else `404`.
- Every HTML answer carries `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` and a
  content security policy that lets the page reach its own origin only:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval' 'sha256-...'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`.
  The one loosening is the `'sha256-...'` sources: the viewer's `index.html` carries inline scripts
  (its first-paint appearance, and the build's table of chunk ids), and the Worker hashes each one
  in the HTML it serves, so the policy follows the build without `'unsafe-inline'`.
- No answer carries CORS headers: nothing but the page itself and the command calls the API.

## What it keeps, and what it never keeps

It keeps, per share: the ciphertext, the hashes of the write and delete secrets, the format and the
expiry. Nothing else: no address, no name, no account, no log of reads.

It never keeps the key or either secret. The key passes through the Worker during an upload, is
imported (non-extractable) to encrypt that one body, and goes out of scope with the request; it is
neither stored nor logged, and the Worker logs no header and no body. Cloudflare's own per-request
log is off (`observability.logs.invocation_logs: false`), and the headers Cloudflare's tail shows
are redacted for names that contain `auth` or `key`.

This is encryption at rest under a key only the link holds: someone who reads the bucket alone
cannot open a share. It is not encryption on the author's computer: the key reaches the service with
each upload, so whoever runs the Worker could, by changing its code, keep keys from then on. Anyone
with the view link can open the share; anyone with the delete link (or the author's write secret)
can delete it.

## Set-up, once

1. **A Cloudflare account on the Workers Paid plan.** The free plan's 10 ms of CPU a request is too
   little to encrypt a large upload.
2. **The bucket.** `npx wrangler@4.167.0 r2 bucket create cad-shares`.
3. **The backstop.** An R2 lifecycle rule deleting every object 8 days after upload, behind the
   Worker's own 7-day expiry (which is enforced on every read): a share nobody reads again is still
   gone. `npx wrangler@4.167.0 r2 bucket lifecycle add cad-shares delete-after-8-days --expire-days 8`
   (no prefix: every object), then `npx wrangler@4.167.0 r2 bucket lifecycle list cad-shares` to
   check; or in the dashboard, R2 object storage, `cad-shares`, Settings, Object Lifecycle Rules,
   Add rule. R2 deletes an expired object within about a day.
4. **The secrets and the origin**, in GitHub, Settings, Secrets and variables, Actions:
   `CLOUDFLARE_API_TOKEN` (an account API token with the "Edit Cloudflare Workers" permissions,
   scoped to this account) and `CLOUDFLARE_ACCOUNT_ID` as secrets, and `SHARE_ORIGIN` as a
   variable: `https://cad.fun` once the domain is attached, and until then the Worker's own address,
   `https://cad-share.<account subdomain>.workers.dev`. Then run `Deploy Share`
   (`gh workflow run deploy-share.yml --ref main`).
5. **The domain.** After the first deploy: in the dashboard, Workers & Pages, `cad-share`,
   Settings, Domains & Routes, Add, Custom Domain, `cad.fun`. The zone must be on the same Cloudflare
   account; Cloudflare makes the DNS record. `wrangler.jsonc` names no route, which is how Wrangler
   leaves routes to the dashboard, so a deploy keeps the domain attached; it keeps the `workers.dev`
   address on too (`workers_dev: true`). Set `SHARE_ORIGIN` to `https://cad.fun` and deploy again
   to check it.
6. **A billing alert.** In the dashboard, Manage Account, Billing, Billable Usage, Create budget
   alert, at a monthly amount you would notice (a Pay-as-you-go account's). R2 storage, R2
   operations and Worker requests are billed by use; the rate limit (10 uploads and deletes a minute per address and location) and the
   size cap bound what one client can do, not what many can.

## Taking a share down

Its delete link does it, in a browser, or the command that made it. Without either, delete the
object by its id (the path of the link, before `#`):

```bash
npx wrangler@4.167.0 r2 object delete cad-shares/<id> --remote
```

The page then answers that the share has expired or was deleted. A share cannot be kept from being
uploaded again by whoever holds its write secret; a takedown that must hold also needs that id
refused, which is a change to the Worker.

## Cloudflare, as relied on

Checked against Cloudflare's documentation on 2026-11-24:

- Static assets: `assets.directory`, `binding`, `run_worker_first` (an array of patterns, `*`
  matching deeply, `!` excluding), `html_handling: "none"`, `not_found_handling: "none"`; a request
  matching no asset invokes the Worker; `env.ASSETS.fetch()` reads only the URL's path.
  [Binding](https://developers.cloudflare.com/workers/static-assets/binding/),
  [Worker script routing](https://developers.cloudflare.com/workers/static-assets/routing/worker-script/),
  [HTML handling](https://developers.cloudflare.com/workers/static-assets/routing/advanced/html-handling/),
  [configuration](https://developers.cloudflare.com/workers/wrangler/configuration/).
- R2 from a Worker: `put(key, value, { onlyIf, customMetadata, httpMetadata })` returns `null` when
  the condition fails; `onlyIf` takes an `R2Conditional` (`etagMatches`, ...) or a `Headers` of
  conditional headers, all but `If-Range`; `head()` and `get()` return `null` for no object;
  `delete(key)`. [Workers API reference](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/);
  wildcard etags in conditional headers (so `If-None-Match: *` puts only if absent):
  [release notes, 2023-06-16](https://developers.cloudflare.com/r2/platform/release-notes/).
- Rate limiting: the `ratelimits` binding (`name`, `namespace_id`, `simple: { limit, period }`,
  period 10 or 60), `limit({ key })` returning `{ success }`, counted per Cloudflare location and
  approximate; Wrangler 4.36.0 or later.
  [Rate limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/).
  The page advises against keying by IP address, since many people can share one; the service does
  so anyway, because a share has no account to key by, and the limit is set high enough for that.
- The client's address: `CF-Connecting-IP`, the address that connected to Cloudflare.
  [HTTP request headers](https://developers.cloudflare.com/fundamentals/reference/http-request-headers/).
- Logs: `observability.logs.invocation_logs`
  ([Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/));
  tail events redact header values whose names contain `auth`, `key`, `secret`, `token` or `jwt`
  ([Tail handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/)).
- Limits: CPU time 10 ms a request on Free, 30 s by default on Paid; 128 MB of memory an isolate;
  request bodies up to 100 MB on the Free and Pro zone plans.
  [Limits](https://developers.cloudflare.com/workers/platform/limits/).
- Wrangler: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment
  ([system environment variables](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/));
  `r2 bucket create`, `r2 bucket lifecycle add <BUCKET> [NAME] [PREFIX] --expire-days`, `r2 object
  delete <bucket>/<key> --remote` ([R2 commands](https://developers.cloudflare.com/workers/wrangler/commands/r2/));
  the token's permissions ([GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)).
- Routes left to the dashboard when the configuration names none
  ([deprecations](https://developers.cloudflare.com/workers/wrangler/deprecations/)).
- Lifecycle rules ([object lifecycles](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)),
  custom domains ([Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)),
  budget alerts ([Budget alerts](https://developers.cloudflare.com/billing/manage/budget-alerts/)).
