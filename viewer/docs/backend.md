# Backend Storage

CAD Viewer uses a small backend interface so the same React app can run against
local files during development and hosted object storage in deployment. Client
code talks to HTTP routes and catalog URLs; it does not read filesystem paths
directly.

## Interface

Backend implementations expose this core shape:

```js
{
  kind,
  readCatalog({ rootDir, fileRef }),
  refreshCatalog({ rootDir, fileRef }),
  resolveFileAssetAccess({ fileRef, asset, catalog }),
}
```

Trusted upload tooling for hosted storage serializes catalog JSON and uploads it
as `catalog.json`. Writable backends may expose
`writeAsset({ fileRef, body, contentType })` and
`generateStepArtifact({ fileRef, force, catalog })`.

Local filesystem backends also expose helpers used by Vite and the local
production server:

```js
{
  resolveRoot(rootDir),
  openFileAsset({ fileRef, asset, catalog }),
  assetPathForFileRef(fileRef, { resolvedRoot }),
  entryForSourcePath(catalog, resolvedRoot, sourcePath),
  contentTypeForPath(filePath),
}
```

`readCatalog()` returns catalog JSON from the backend's source of truth.
`refreshCatalog()` lets an adapter update or regenerate that in-memory view.
Writable helpers may write servable CAD assets such as hidden STEP GLBs or run
local CAD generation.

## Local Filesystem

`src/server/localAssetBackend.mjs` is the development and local deployment
implementation. `readCatalog()` and `refreshCatalog()` scan
the absolute `?dir=` root for the current request, keep the catalog as an
in-memory object, and return schema v4 entries whose `file` values are absolute
paths plus `rootRelativeFile` values for URL navigation. The local backend does
not write `catalog.json` or any hidden catalog cache file.

Local filesystem deployments are intentionally URL-driven. `?dir=` may be
absolute or relative to the directory where the Viewer was started; when omitted
it defaults to that startup directory. The startup directory is also the first
active workspace. `?file=` values are always relative to the active `?dir=`
workspace. `VIEWER_LOCAL_ROOT_DIR`, `VIEWER_LOCAL_WORKSPACE_ROOT`, and the old
fixed-root startup flag have been removed and now fail at startup.

The local backend serves asset bytes from the active root and writes regenerated
artifacts back into it. It rejects path traversal and only serves or writes
supported CAD Viewer asset types.

Local STEP GLB/topology regeneration calls the Python `cadpy` package. The root
viewer carries a generated, installable copy under `viewer/packages/cadpy`; run
`scripts/bundle/bundle-skill.sh cad-viewer` after changing `packages/cadpy`, then
install `viewer/requirements.txt` into the Python runtime used by the viewer.
The generated cad-viewer skill runtime bundles that same installable package
under `scripts/viewer/packages/cadpy` and does not need the repository root.

Vite dev mounts this backend for:

- `GET /__cad/server`
- `GET /__cad/catalog`
- `GET /__cad/asset?file=...`
- `GET /__cad/download?file=...&asset=output|source`
- `POST /__cad/reveal?file=...&asset=output|source`
- `POST /__cad/step-artifact`

`download` streams the requested asset bytes and works for both local and hosted
deployments. `reveal` opens the asset in Finder or the platform file manager and
is only available for the local filesystem backend. `asset=output` resolves the
catalog entry file itself; `asset=source` resolves optional source code, such as
a same-stem Python generator for Python-backed STEP files.

The local production server uses the same backend:

```bash
npm run build
npm run serve
```

Then open the printed server URL with
`?dir=/absolute/root&file=model.step`. Pass `--port <number>` to
`npm run serve --` only when the default production port is already in use.

## Vercel Blob

`src/server/vercelBlobAssetBackend.mjs` is the hosted storage adapter. Vercel
deployments construct it in read-only mode: the hosted API reads the catalog and
serves public Blob assets, but it does not write Blob objects or regenerate STEP
artifacts.

Expected deployment shape:

- Build the frontend normally.
- Run a trusted local upload/maintenance script to publish supported assets and a
  schema v4 `catalog.json` containing public Blob URLs.
- Deploy the viewer with `VIEWER_ASSET_BACKEND=vercel-blob` and a read-only
  catalog configuration. Catalog warnings such as stale STEP artifacts are shown
  in the UI instead of being fixed by the hosted app.
- Hosted Vercel routes ignore local filesystem `?dir=` query values and read the
  configured hosted `catalog.json` instead.

The Vercel deployment entrypoints are intentionally thin:

```text
api/cad/server.js
api/cad/catalog.js
api/cad/download.js
api/cad/reveal.js
vercel.json
```

`vercel.json` rewrites the client-facing routes below to those API functions:

```text
/__cad/server
/__cad/catalog
/__cad/download
/__cad/reveal
```

The local production server can mount the Blob catalog path by environment:

```bash
VIEWER_ASSET_BACKEND=vercel-blob \
VIEWER_VERCEL_BLOB_PREFIX=https://<store-id>.public.blob.vercel-storage.com/models2 \
npm run serve
```

Upload a local directory catalog and supported viewer assets with:

```bash
VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN=... \
VIEWER_VERCEL_BLOB_PREFIX=models2 \
npm --prefix viewer run upload:blob -- models
```

`BLOB_READ_WRITE_TOKEN` may be used instead of
`VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN`, matching the environment variable Vercel
Blob integrations create.

The uploader also reads `.vieweruploadignore` from the uploaded directory and
accepts repeated `--ignore-file` options for gitignore-style exclude patterns.
It excludes `mechbench/`, `mechbench2/`, `7dof_arm/`, and Python source files
by default, and public Blob catalogs omit Python source paths and URLs.

For token-free read-only deployments, `VIEWER_VERCEL_BLOB_PREFIX` should be the
public Blob URL for the prefix directory. The hosted backend always reads
`catalog.json` at the root of that prefix. Trusted local upload or maintenance
scripts may use the path prefix, such as `models2`, with a read/write token.

The writable Blob helper methods remain available to local scripts that import
the backend directly and pass a Blob read/write token. They are not exposed by
the hosted Vercel API.
