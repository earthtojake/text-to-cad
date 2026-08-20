# Backend Storage

CAD Viewer uses a small backend interface so the React app talks to HTTP routes
and catalog URLs instead of reading filesystem paths directly. The viewer is a
local-filesystem app; the only backend is the local one.

## Interface

The backend exposes this core shape:

```js
{
  kind,
  readCatalog({ rootDir, fileRef }),
  refreshCatalog({ rootDir, fileRef }),
  resolveFileAssetAccess({ fileRef, asset, catalog }),
}
```

The local backend may also expose
`generateStepArtifact({ fileRef, force, catalog })` to run CAD generation on
demand.

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
`refreshCatalog()` lets the adapter update or regenerate that in-memory view.
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
it defaults to the startup `--dir`, or to the startup directory if `--dir` was
not passed. That default directory is also the first active directory. `?file=`
values are always relative to the active `?dir=` directory.
`VIEWER_LOCAL_ROOT_DIR`, `VIEWER_LOCAL_WORKSPACE_ROOT`, and the old fixed-root
startup flag have been removed and now fail at startup.

The local backend serves asset bytes from the active root and writes regenerated
artifacts back into it. It rejects path traversal and only serves or writes
supported CAD Viewer asset types.

Local STEP GLB/topology regeneration calls the Python `cadgen` package. This app
carries an installable copy under `packages/cadgen`, so regeneration works from
this directory alone — install `requirements.txt` into the Python runtime used
by the viewer:

```bash
python -m pip install -r requirements.txt
```

Before binding its HTTP port, the Viewer validates that its selected Python can
import `OCP`, `build123d`, and `cadgen.step_artifact_cli`. Startup fails instead of
serving a Viewer that cannot build missing artifacts. Set
`VIEWER_CAD_PYTHON=/absolute/path/to/python` when the CAD environment is not in
the checkout's `.venv`.

Vite dev mounts this backend for:

- `GET /__cad/server`
- `GET /__cad/catalog`
- `GET /__cad/asset?file=...`
- `GET /__cad/download?file=...&asset=output|source`
- `POST /__cad/reveal?file=...&asset=output|source`
- `POST /__cad/step-artifact`

`download` streams the requested asset bytes from the local backend. `reveal`
opens the asset in Finder or the platform file manager. `asset=output` resolves
the catalog entry file itself; `asset=source` resolves optional source code, such
as a same-stem Python generator for Python-backed STEP files.

The local production server uses the same backend:

```bash
npm run build
npm run serve
```

Then open the printed server URL with
`?dir=/absolute/root&file=model.step`. Pass `--port <number>` to
`npm run serve --` only when the default production port is already in use.
