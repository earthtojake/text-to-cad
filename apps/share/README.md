# Share

`cad.fun`: where a shared model lives. A share is two things under one id: its **view**, the
document's view bundle, which a browser draws, and **the files that made it**: a model's `.xbf`, its
script, the modules its build imported and the files it read, or a file document's file with what it draws
from (a robot description's meshes; a KiCad board's or schematic's project). `cad share` uploads
the files of both that its share does not hold yet, in packs, then commits a manifest that says
where each file lies, so a share costs what changed. Anyone with the link (`https://cad.fun/<id>`)
opens it in the hosted viewer, with no sign-in, and downloads the files that made it as a zip
(`https://cad.fun/<id>.zip`). A share expires 7 days after its last commit. The service is a
Cloudflare Worker of its own (`cad-share`) over an R2 bucket (`cad-shares`), serving the viewer's
built client as its static assets.

**PURPOSE** — keep a share, sealed, for 7 days; hand its bytes to whoever has its link; and serve
the page that opens it and the zip of the files that made it. Its routes, statuses, headers and
formats (`cad-share/2`) are a contract with every released `cad share` and `cad import` and with the
page: they never break.

**MAY DEPEND ON** — Cloudflare Workers' runtime (the web-standard `Request`, `Response` and
`crypto.subtle`), its R2, static assets and rate limiting bindings, and Node's standard library for
the local runner and the tests: no npm dependencies, so there is nothing to install. It is not one
of the root npm workspaces and has no lockfile. Its static assets are `apps/web`'s build output,
copied in before a deploy; it imports nothing of any app or package.

**DEPENDED ON BY** — nothing in the repo imports it. `cad share` and `cad import` (`packages/cad`)
reach it over HTTPS (`CAD_SHARE_URL` points them at another origin), and the viewer's share mode
(`apps/web`, `packages/core`) is the page it serves at `/<id>`.

## Build, run, deploy

```
src/worker.mjs  # the Worker: the whole service, a fetch(request, env, ctx) handler
src/local.mjs   # the platform, locally: stand-ins for R2, the static assets, the limiters, the routing
serve.mjs       # the local runner: the real Worker over Node's http
build.mjs       # copies apps/web's build into viewer/, the Worker's static assets (ignored), with _headers
wrangler.jsonc  # the Worker, its bucket, its two limiters, its assets, its four variables
```

```bash
npm --prefix apps/share test          # or scripts/test/test-share.sh, which CI runs (static)
npm run build:web                     # at the root, after npm ci: the viewer, into apps/web/dist
npm --prefix apps/share run build     # apps/web/dist -> apps/share/viewer
node apps/share/serve.mjs --port 8787 --assets apps/share/viewer [--store tmp/share]
```

`serve.mjs` serves `src/worker.mjs` itself, over stand-ins that do what the Worker asks of
Cloudflare: an R2 bucket in memory (or files under `--store`) whose `put` honours `onlyIf`
(`etagMatches`, `If-None-Match: *`) and keeps custom metadata, whose `list` answers by prefix,
page by page, with `truncated` and a cursor, and whose `delete` takes up to 1000 keys; an assets
binding over the folder given that answers exactly what `wrangler.jsonc`'s `html_handling: "none"`
answers, adding to each file it serves what the folder's `_headers` names; the asset-first routing
and `run_worker_first` read from `wrangler.jsonc`; `CF-Connecting-IP` set from the socket; and the
two limiters, which allow everything. A stand-in throws on an option it does not emulate rather than
answering otherwise than R2. As Cloudflare does, it sends an answer's headers at once and its body
as the client reads it, and cuts off a body that fails part way rather than ending it as if whole.
`--port 0` takes any free port. When it is ready it prints its origin, and nothing else, on one
line (`http://127.0.0.1:8787`); point `CAD_SHARE_URL` there. It stops on SIGINT or SIGTERM.

Deployment is the `Deploy Share` workflow only (`.github/workflows/deploy-share.yml`), on
dispatch: it runs the tests, builds the viewer, copies it in, deploys with Wrangler (pinned, through
`npx`), and then asks `SHARE_ORIGIN` that `/` redirects and an unknown share is `404`.

## The API

Every answer that is not a share's bytes is JSON. A refusal is `{"error": "...", "hint": "..."}`
with its status: `error` a fixed word for a program, `hint` a sentence for a person. Every answer,
the pages' and the files' too, carries `X-Robots-Tag: noindex, nofollow`; none carries CORS headers.

| Value | Made by | Form |
| --- | --- | --- |
| share id | the command | 16 random bytes, base64url without padding: 22 characters, `^[A-Za-z0-9_-]{22}$`; the command draws again while they begin with `-`, which a command line reads as an option |
| write secret | the command | 32 random bytes, base64url, 43 characters: upload again |
| delete secret | the command | 32 random bytes, base64url, 43 characters: delete |
| key | the service and the page | derived from the id: the AES-256-GCM key every stored object is sealed with |
| name | the service | derived from the id, 64 lowercase hex characters: where the share is stored |

**The id is the capability**: whoever has the link can open the model. The key and the name are
HKDF-SHA256 (RFC 5869) of the id: input keying material the UTF-8 bytes of its 22 characters, salt
the UTF-8 bytes of `cad-share/2`, info `key` or `name`, 32 bytes of output. The service keeps
neither secret, only the lowercase hex SHA-256 of each one's text, the 43 characters as they
travel; it never keeps the id or the key.

**`PUT /v1/shares/<id>/packs/<pack id>`**, a pack: `Authorization: Bearer <write secret>`,
`Cad-Delete-Hash: <hex SHA-256 of the delete secret>`, a `Content-Length`, and the pack as the body.
The pack id is the lowercase hex SHA-256 of the pack's bytes.

| Status | `error` | When |
| --- | --- | --- |
| `201` | | Stored: `{"pack", "bytes"}`, `bytes` the size stored. Stored again, it is the same bytes |
| `400` | `bad_id`, `bad_pack_id`, `bad_secret`, `bad_delete_hash`, `bad_pack` | The id, the pack id, the secret or the hash malformed; a body whose SHA-256 is not its pack id |
| `401` | `unauthorized` | No `Authorization: Bearer` |
| `403` | `forbidden` | The share's owner holds another write secret's hash |
| `411` | `length_required` | No `Content-Length` |
| `413` | `too_large` | Over `MAX_PACK_BYTES`, by its length or by its body |
| `429` | `rate_limited` | More packs and zips from this address than `LIMITER_PACKS` allows (`Retry-After: 60`) |

**`PUT /v1/shares/<id>`**, a commit: the same headers with `Content-Type: application/json`, and
the [share manifest](#the-share-manifest-cad-share2) as the body.

| Status | `error` | When |
| --- | --- | --- |
| `201` | | The share's first manifest, or its first since the last expired: `{"id", "expires", "bytes", "files"}`, `expires` ISO 8601, `bytes` the stored size of the packs it names, `files` how many files its view and its files list together |
| `200` | | One replaced, the same body: the 7 days start again |
| `400` | `bad_id`, `bad_secret`, `bad_delete_hash`, `bad_manifest` | As a pack's; a manifest not of its shape, the hint saying what |
| `401`, `403`, `411` | | As a pack's |
| `409` | `missing_packs` | It names packs the share does not hold: `{"error", "hint", "missing": ["<pack id>", ...]}`, each once, sorted |
| `409` | `conflict` | Another commit replaced the share's manifest while this one was checked: no `missing`; commit again |
| `413` | `too_large`, `share_too_large` | Over `MAX_MANIFEST_BYTES`, by its length or by its body; the packs it names hold more than `MAX_SHARE_BYTES` |
| `429` | `rate_limited` | More commits and deletes from this address than `LIMITER` allows (`Retry-After: 60`) |

**`GET /v1/shares/<id>`** (and `HEAD`): the sealed manifest, `Content-Type: application/octet-stream`,
`Cache-Control: no-store`, `Cad-Share-Expires: <ISO 8601>`. `404` (`not_found`) for a share with no
manifest, whether it never had one, expired or was deleted; `400` for a malformed id.

**`GET /v1/shares/<id>/packs/<pack id>`** (and `HEAD`): the sealed pack, `Content-Type:
application/octet-stream`, `Cache-Control: private, max-age=604800, immutable`. `404` when the share
has no live manifest or holds no such pack; `400` for a malformed id or pack id.

**`DELETE /v1/shares/<id>`**: `Authorization: Bearer <delete secret or write secret>`. `204` when
deleted, every object of the share with it; `404` for no owner; `403` for a secret that matches
neither hash, `401` for none, `400` for a malformed one; `429` past `LIMITER`.

Another method on a route is `405` with `Allow`; any other `/v1` path is `404`.

## The share manifest (`cad-share/2`)

```json
{
  "format": "cad-share/2",
  "name": "juno",
  "entry": "juno.py",
  "made": { "cad": "0.11.17", "build123d": "0.13.0", "python": "3.13.18", "system": "Linux", "arch": "x86_64" },
  "view": {
    "manifest.json": { "sha256": "<64 hex>", "bytes": 1234, "at": [["<pack id>", 0, 456]] }
  },
  "files": {
    "juno.py": { "sha256": "<64 hex>", "bytes": 5120, "at": [["<pack id>", 456, 1800]] },
    "juno.xbf": { "sha256": "<64 hex>", "bytes": 98304, "at": [["<pack id>", 2256, 61410]] }
  }
}
```

`view` is every file of the bundle by its path, and `files` every file that made it by its path
from the files' root, a model's `.xbf` among them (the command decides which; the service takes them
as given). In both,
`sha256` and `bytes` are the file's own bytes, uncompressed, and `at` the ranges of packs,
`[pack id, offset, length]` into a pack's bytes before sealing, whose bytes, joined in order, are
the file's gzip member; two entries of the same content may name the same ranges. `name` is the
document's, `entry` the path in `files` of the script that builds a model, and `made` what built
it, each value text; a file document's `entry` and `made` are `null`. A commit refuses (`400`) a
manifest that is not:

- a JSON object, in UTF-8, of `format` (`"cad-share/2"`), `name`, `entry`, `made`, `view` and
  `files`, each there and no other (a manifest of `format` and `files` alone, the bundle's, is
  refused);
- `name` text of 1 to 200 characters, none a control character;
- `entry` `null`, or a path that `files` lists;
- `made` `null`, or an object of at most 32 members, each name and value text of at most 100
  characters;
- `view` an object listing `manifest.json`, and not `thumbnail.png`, which is left out of a share (it
  may show an earlier version of the document); `files` an object, which may be empty, and may list
  a path `view` lists too (a `thumbnail.png` the build read among them); at most 200,000 files in
  both together;
- in both, each path relative and `/` separated: no empty, `.` or `..` segment, no leading `/`, no
  `\`, no drive (`C:`), well-formed text of at most 1024 bytes in UTF-8;
- in both, no path in a version control's folder (`.git`, `.hg`, `.svn`, `.bzr`, `_darcs`, `.jj`,
  `.pijul`, Fossil's `.fslckout` and `_FOSSIL_`), as any system compares a name: in any case, with the
  dots and spaces Windows drops from its end, before an NTFS stream's `:`, without the code points HFS+
  ignores, and as Windows' short name (`GIT~1`); and no `HEAD` beside an `objects` and a `refs` folder,
  a repository's bare form, which git finds wherever it lies. An import writes the files into a folder,
  and a command run there later (`git status`, a shell prompt's) would run what such a folder's
  settings name;
- in both, each file `sha256`, `bytes` and `at` alone: 64 lowercase hex characters, a whole number,
  and one or more ranges of a pack id and two whole numbers, each inside its pack (checked once the
  pack is found).

Everything a commit does with the packs a manifest names, it does with those of both maps: it
refuses (`409`) one that names a pack the share lacks, counts each pack once in the share's size,
keeps them and the replaced manifest's, and stores them again ahead of the backstop. It cannot read
what a pack holds: a file's size and SHA-256 are for the page to check.

## The files' zip

**`GET /<id>.zip`** (and `HEAD`), `<id>` a share's id: the files that made it, as a zip, made from
the stored members as it is sent. The page links to it; `cad import` downloads it.

| Status | `error` | When |
| --- | --- | --- |
| `200` | | The zip: `Content-Type: application/zip`, `Content-Disposition: attachment; filename="<name>.zip"`, `Cache-Control: no-store`, and `Cad-Share-Entry` and `Cad-Share-Made` where the manifest has an `entry` and a `made` of one member or more. A `HEAD` has the same headers and no body |
| `404` | `not_found` | As a share's other reads: no live manifest (an expired one deletes the share), or one of the bundle alone |
| `405` | `method_not_allowed` | Another method than `GET` and `HEAD` |
| `429` | `rate_limited` | A zip, `GET` or `HEAD`, counts as a pack in `LIMITER_PACKS`: past it (`Retry-After: 60`) |

- **The name**: the manifest's `name` made safe, letters, digits, `.`, `-` and `_` kept and every
  other character `_`, no `.` at either end, at most 100 characters, `share` where nothing is left.
  It names the file and the zip's one folder: `juno.zip` holds `juno/juno.py`, `juno/lib/head.py`.
- **`Cad-Share-Entry: <entry>`**, and **`Cad-Share-Made: <name>=<value>, ...`** in the manifest's
  order. Each path, name and value is percent-encoded UTF-8: every byte but letters, digits and
  `-._~/+` is `%XX`, so `juno.py` and `0.13.0` travel as they are, any text can travel, and `,` and
  `=` part the members alone. A percent-decoder (`urllib.parse.unquote`) reads them back.
- **What it holds**: the folder, then every file of `files` under it, sorted by the bytes of its
  path, and nothing of `view`; a share with no files is a zip of the empty folder. Each name is
  UTF-8 (flag bit 11), each time 1980-01-01 00:00, each file `rw-r--r--` and the folder
  `rwxr-xr-x`, made on UNIX, so a share's zip is the same bytes each time it is asked for.
- **Not compressed again**: a member of the plain form the command writes (RFC 1952 with FLG 0: no
  name, no extra) holds a deflate stream, its bytes but its 10-byte header and its 8-byte trailer,
  and that trailer the CRC-32 and the size (modulo 2^32: the entry's `bytes` where it agrees, for a
  file of 4 GiB or more). Each becomes an entry of method 8 with that CRC-32 and those sizes, its
  data the member's own bytes. A member of any other form is inflated and stored (method 0), its
  CRC-32 computed: inflated once for that, which its header goes before, and again for its bytes.
- **Zip64** where a size or an offset reaches 0xFFFFFFFF, or the entries 0xFFFF: the sizes in an
  extra field of the local header and the central directory, the offset in the latter, and the
  Zip64 end records before the last.
- **As it goes**: the zip is a stream, made as it is read; it reads the manifest, then each pack the
  files name when one of them needs it, and keeps the two it last read: a zip holds two packs at
  most, whatever the share's size. A member split over packs is read range by range. Where a pack
  is missing or a member does not inflate, the zip fails part way, cut off rather than ended as if
  whole. Nothing of it is cached or logged.

## What it stores

Under `s/<name>/`, and nothing else:

- `s/<name>/owner`: no body, and the custom metadata `{format, write, delete}`, the hashes the
  share's first authorised write (a pack or a commit) carried. It is put only if absent
  (`If-None-Match: *`); a write that loses that race reads the owner made, and goes on only if it
  holds the same write hash. A later write's `Cad-Delete-Hash` is checked for its form, not kept.
- `s/<name>/manifest`: the share manifest sealed, `IV || AES-256-GCM(key, IV, manifest, AAD)` with
  the AAD `cad-share/2 manifest`; custom metadata `{format, expires, bytes, files}`.
- `s/<name>/p/<pack id>`: a pack sealed the same way, its AAD `cad-share/2 pack <pack id>`.

Each IV is 12 fresh random bytes, and the 16-byte tag ends the object, as Web Crypto writes it. The
service seals; the page opens.

A commit reads the manifest it replaces, lists the share's packs (by prefix, page by page), checks
that it names none the share lacks and that they fit, and puts its manifest only if the stored one
is still the one it read (`etagMatches`, or `If-None-Match: *` where there was none): no commit
overwrites a manifest it did not see. Then it deletes, in calls of up to 1000 keys, the share's
packs that neither its manifest nor the one it replaced names, in its view or its files; the
replaced one's are kept a commit longer, for a page that opened it or a zip of it still being read.
A manifest past its expiry is no share's: a commit over it answers `201` and keeps none of its
packs.

A read of a share whose manifest is past its expiry, of the manifest, of a pack or of its zip,
deletes the whole share (every object under `s/<name>/`, the manifest first and the owner last) and
answers `404`. A delete does the same at once.

**The backstop.** The bucket's lifecycle rule deletes every object 8 days after its upload, the one
time R2 keeps of an object ([Set-up](#set-up-once)): what a share leaves behind is gone by then,
read or not. A commit keeps its owner and the packs its manifest names from earlier uploads, so it
stores again, unchanged, each of those the rule would delete before the share expires, by a put
conditional on its etag (nothing deleted meanwhile comes back). An object uploaded less than a day
before the commit (the rule's 8 days less the share's 7) is not stored again. `BACKSTOP_DAYS`
(`src/worker.mjs`) is the rule's age.

## Limits

| Variable | Default | What it bounds |
| --- | --- | --- |
| `MAX_PACK_BYTES` | 8 MiB | A pack (the command closes one at 4 MiB) |
| `MAX_MANIFEST_BYTES` | 16 MiB | A share manifest's JSON |
| `MAX_SHARE_BYTES` | 256 MiB | The stored size of the packs a share's manifest names |
| `EXPIRY_DAYS` | 7 | A share's life after its last commit: below the backstop's 8 days |

They are `wrangler.jsonc`'s `vars`; a value that is no positive number is the default. Two rate
limiters count per client address and Cloudflare location: `LIMITER`, commits and deletes, 10 a
minute, and `LIMITER_PACKS`, pack uploads and zips, 60 a minute. The other reads are not counted.
The protocol fixes the rest: 200,000 files a manifest, its view's and its files' together; 1024
bytes a path; 200 characters a name; 32 members of `made`, each name and value 100 characters.

## The pages

- `GET /` redirects (`302`) to `https://www.texttocad.dev`.
- `GET /<id>`, a path that is one share id: the viewer's `index.html`, whatever the fragment. The
  page derives the key from the id, fetches the manifest and the packs its view names from this
  origin, and opens them; `#delete=<secret>` offers the delete. A browser never sends a fragment to
  a server. Beside it, `/<id>.zip` is [the files' zip](#the-files-zip), which the page links to.
- Any other path: the viewer's own files (scripts, styles, images), else `404`. A file is served
  without the Worker, so it carries `X-Robots-Tag` by the `_headers` that `build.mjs` writes beside
  the viewer.
- Every HTML answer carries `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` and a
  content security policy that lets the page reach its own origin only:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval' 'sha256-...'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`.
  The one loosening is the `'sha256-...'` sources: the viewer's `index.html` carries inline scripts
  (its first-paint appearance, and the build's table of chunk ids), and the Worker hashes each one
  in the HTML it serves, so the policy follows the build without `'unsafe-inline'`.
- No answer carries CORS headers: nothing but the page itself and the command calls the API.

## What it keeps, and what it never keeps

It keeps, per share: its sealed manifest and packs, the hashes of the write and delete secrets, and
the manifest's format, expiry, size and number of files. Nothing else: no id, no address, no name,
no account, no log of reads.

It never keeps the id, the key or either secret. Every request names the id in its path; the Worker
derives the key (imported non-extractable) and the name from it for that request alone, and stores
and logs neither. The Worker logs no path, no header and no body. Cloudflare's own per-request log
is off (`observability.logs.invocation_logs: false`); a live tail of the Worker (`wrangler tail`)
shows each request's path, and with it the id, to whoever runs the service.

This is encryption at rest under a key only the link holds: someone who reads the bucket alone can
neither open a share nor tell which link it belongs to, its name being a one-way function of the
id. It is not encryption on the author's computer: the service seals, so whoever runs the Worker
could, by changing its code, keep ids from then on. Anyone with the view link can open the share
and download the files that made it; anyone with the delete link (or the author's write secret) can
delete it.

## Set-up, once

1. **A Cloudflare account on the Workers Paid plan.** The free plan's 10 ms of CPU a request is too
   little to seal a large pack or check a large manifest.
2. **The bucket.** `npx wrangler@4.167.0 r2 bucket create cad-shares`.
3. **The backstop.** An R2 lifecycle rule deleting every object 8 days after upload, behind the
   Worker's own 7-day expiry (which is enforced on every read): a share nobody reads again is still
   gone. `npx wrangler@4.167.0 r2 bucket lifecycle add cad-shares delete-after-8-days --expire-days 8`
   (no prefix: every object), then `npx wrangler@4.167.0 r2 bucket lifecycle list cad-shares` to
   check; or in the dashboard, R2 object storage, `cad-shares`, Settings, Object Lifecycle Rules,
   Add rule. R2 deletes an expired object within about a day. Never make the rule shorter than the
   Worker's `BACKSTOP_DAYS` (8): it would delete what a live share keeps.
4. **The secrets and the origin**, in GitHub, Settings, Secrets and variables, Actions:
   `CLOUDFLARE_API_TOKEN` (an account API token with the "Edit Cloudflare Workers" permissions,
   scoped to this account) and `CLOUDFLARE_ACCOUNT_ID` as secrets, and `SHARE_ORIGIN` as a
   variable: `https://cad.fun` once the domain is attached, and until then the Worker's own address,
   `https://cad-share.<account subdomain>.workers.dev`. Then run `Deploy Share`
   (`gh workflow run deploy-share.yml --ref main`). The two rate limiters and the four variables
   come with the deploy, as `wrangler.jsonc` declares them: nothing is made by hand. The limiters'
   namespace ids (`47201`, `47202`) are numbers of this account's choosing, which no other Worker of
   the account may use; a limit is changed there and deployed.
5. **The domain.** After the first deploy: in the dashboard, Workers & Pages, `cad-share`,
   Settings, Domains & Routes, Add, Custom Domain, `cad.fun`. The zone must be on the same Cloudflare
   account; Cloudflare makes the DNS record. `wrangler.jsonc` names no route, which is how Wrangler
   leaves routes to the dashboard, so a deploy keeps the domain attached; it keeps the `workers.dev`
   address on too (`workers_dev: true`). Set `SHARE_ORIGIN` to `https://cad.fun` and deploy again
   to check it.
6. **A billing alert.** In the dashboard, Manage Account, Billing, Billable Usage, Create budget
   alert, at a monthly amount you would notice (a Pay-as-you-go account's). R2 storage, R2
   operations and Worker requests are billed by use; the rate limits (per address and location, 10
   commits and deletes and 60 packs a minute) and the size caps bound what one client can do, not
   what many can.

## Taking a share down

Its delete link does it, in a browser, or the command that made it. Without either, delete its
manifest: the share is unreadable at once (its packs are served beside a live manifest only), and
the backstop deletes the rest within 8 days. The id is the link's path; its name, the Worker's own
derivation:

```bash
name="$(node --input-type=module -e 'import { nameOf } from "./apps/share/src/worker.mjs"; console.log(await nameOf(process.argv[1]))' <id>)"
npx wrangler@4.167.0 r2 object delete "cad-shares/s/$name/manifest" --remote
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
  A `_headers` file in the assets' folder: a path pattern on a line (`*` a splat), its headers
  indented below it, rules in order and a header given twice joined with a comma; applied to the
  files served without the Worker and never to the Worker's own answers; not itself served.
  [Headers](https://developers.cloudflare.com/workers/static-assets/headers/).
- R2 from a Worker: `put(key, value, { onlyIf, customMetadata, httpMetadata })` returns `null` when
  the condition fails; `onlyIf` takes an `R2Conditional` (`etagMatches`, ...) or a `Headers` of
  conditional headers; `head()` and `get()` return `null` for no object; `delete()` takes up to
  1000 keys a call; `list({ prefix, cursor, include })` answers up to 1000 objects in lexicographic
  order, and may answer fewer, `truncated` saying whether more follow and `cursor` (present only
  then) where to go on; a listed object's custom metadata only where `include` asks for it.
  [Workers API reference](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/).
  Writes, deletes and lists are strongly consistent, a condition is evaluated against the bucket's
  committed state, and of puts with `If-None-Match: *` to an absent key at most one succeeds
  ([consistency](https://developers.cloudflare.com/r2/reference/consistency/)); an etag to match
  fails where the key holds nothing, and `If-None-Match: *` succeeds only there
  ([conditional operations](https://developers.cloudflare.com/r2/api/s3/conditional-operations/));
  wildcard etags in conditional headers ([release notes, 2023-06-16](https://developers.cloudflare.com/r2/platform/release-notes/)).
- Lifecycle rules: a prefix, and objects deleted once they reach an age, typically within 24 hours
  of it ([object lifecycles](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)).
- Rate limiting: the `ratelimits` binding (`name`, `namespace_id`, `simple: { limit, period }`,
  period 10 or 60), `limit({ key })` returning `{ success }`, counted per Cloudflare location and
  approximate; Wrangler 4.36.0 or later.
  [Rate limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/).
  The page advises against keying by IP address, since many people can share one; the service does
  so anyway, because a share has no account to key by, and the limits are set high enough for that.
- The client's address: `CF-Connecting-IP`, the address that connected to Cloudflare.
  [HTTP request headers](https://developers.cloudflare.com/fundamentals/reference/http-request-headers/).
- Web Crypto: HKDF (`importKey`, `deriveBits`) and AES-GCM in `crypto.subtle`.
  [Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/).
- `DecompressionStream`, with `gzip` among its formats
  ([Web standards](https://developers.cloudflare.com/workers/runtime-apis/web-standards/)); a
  `Response` whose body is a `ReadableStream` is sent as it comes, after its status and headers, and
  the Worker runs on until it is complete or the client goes, within its 128 MB
  ([Streams](https://developers.cloudflare.com/workers/runtime-apis/streams/)).
- Logs: `observability.logs.invocation_logs`
  ([Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/));
  tail events redact header values whose names contain `auth`, `key`, `secret`, `token` or `jwt`
  ([Tail handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/)).
- Limits: CPU time 10 ms a request on Free, 30 s by default on Paid; 128 MB of memory an isolate;
  request bodies up to 100 MB on the Free and Pro zone plans; 10,000 subrequests an invocation on
  Paid and six connections at once waiting for headers, R2's calls among both.
  [Limits](https://developers.cloudflare.com/workers/platform/limits/).
- Wrangler: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment
  ([system environment variables](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/));
  `r2 bucket create`, `r2 bucket lifecycle add <BUCKET> [NAME] [PREFIX] --expire-days`, `r2 object
  delete <bucket>/<key> --remote` ([R2 commands](https://developers.cloudflare.com/workers/wrangler/commands/r2/));
  the token's permissions ([GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)).
- Routes left to the dashboard when the configuration names none
  ([deprecations](https://developers.cloudflare.com/workers/wrangler/deprecations/)).
- Custom domains ([Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)),
  budget alerts ([Budget alerts](https://developers.cloudflare.com/billing/manage/budget-alerts/)).
