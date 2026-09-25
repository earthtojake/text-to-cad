# Backend

The CAD Viewer client never reads filesystem paths. It talks to HTTP routes under
`/__cad/*` and to catalog URLs, and a backend on the other side resolves those to
files. The viewer is a local-filesystem app, so there is exactly one backend.

That backend is **stdlib-only Python**: `server/`, no web framework and no third-party
import, on an interpreter of **3.11 or newer**. It owns everything the viewer does —
the catalog scan, path containment, asset serving, the SPA, artifact status, the STEP
import bridge, the instance registry. The viewer is a STATIC
VISUALIZATION TOOL: its render path runs no CAD kernel. It renders artifacts that
exist — render packages, sibling `.dxf` files — and the CLIs own generation and
export. The one build-shaped thing it does is importing a raw foreign STEP, which
calls cadgen's compile entry point in a worker process (below).

`cadgen` is a SOFT dependency, needed only for that import: nothing under `server/`
imports it at module scope (`tests_server/test_module_boundaries.py` is the fence), so
with no cadgen installed the viewer still scans, serves and renders, and only imports
answer with a hint. The version floor is checked at startup rather than discovered on
the first request — macOS ships 3.9 as `python3`, and on 3.9 the server booted, printed
its URL, and then failed the catalog with a raw `TypeError`. It now refuses to start,
naming the version it needs and how to select another interpreter.

## Where it runs

Both modes run the same `server/main.py`, so a behaviour difference between them
is a bug. It is one implementation reached two ways, not two code paths — dev
adds a proxy hop and nothing else:

- **Dev** (`npm run dev`) — Vite serves the client from source with HMR and spawns
  `server/main.py --ephemeral --no-registry --api-only`, proxying `/__cad` and
  `/__tess_cache` to it. `VIEWER_PYTHON` chooses the interpreter (default `python3`);
  `VIEWER_BACKEND_URL` attaches to a backend you started yourself instead, which is
  how you put a debugger on it. Dev lives on Vite's canonical port (5173), is strict
  about it (taken port → pick another with `--port`), and never enters the instance
  registry — `--no-registry` is what guarantees that, and it is correctness rather
  than tidiness: a registered dev backend would be REUSED by a later real launch on
  the same root, handing an agent a URL served by Vite's proxy target. `--api-only`
  is why dev needs no build first: Vite owns the client here, so this process serves
  only the two API prefixes and the SPA routes answer 404. (`dist/` is gitignored, so
  requiring one made `npm run dev` fail on every fresh clone.)
- **Production** (`npm run build`, then `python server/main.py`) — one process serves
  the built `dist/` and the API, and a missing `dist/` is a hard refusal naming the
  build. The cad-viewer agent skill ships the same files (built dist + this server)
  and starts them the same way; cadgen ships no viewer at all.

## Launching (unconditional, Jupyter-style)

Running `main.py` from a directory always ends with the URL of a live, correct
Viewer for that directory. Order of operations:

1. **Reuse**: unless `--new` (or an explicit `--port`) is given, the launcher looks for
   a registry entry whose `realpath(served directory)` and identity token match,
   identity-probed (`/__cad/server` must answer as the recorded pid). The token is the
   viewer version SALTED with the newest mtime across `server/`'s `.py` files and the
   built `dist/` (`identity_token` in `server/http_app.py`, the shape of cadgen's
   daemon token), recorded at the instance's START — so in a checkout a `git pull` or
   rebuild changes the token and a stale resident simply fails the match, while in a
   published bundle the files never change and this is exactly version-keyed reuse.
   On a match it prints that URL with `action:"reused"` and exits 0. The key is never
   the port or the pid — keying reuse on the port was the old source-blind-reuse bug,
   and keying it on the bare version was its dev-checkout remnant.
2. **Roll**: otherwise it binds the first free port from 3245 upward (binding IS the
   probe; a lost race just moves to the next candidate) and prints `action:"started"`.
3. **Strict `--port`**: an explicit port is a demand — taken means exit 1, naming the
   holder when the registry knows it. No reuse, no rolling.

The printed URL (and `--json`'s `{url,port,action}` line) is the whole contract; the
port is an output of launch. A running instance keeps executing the code it started
with — the mtime salt means an edited/pulled/rebuilt checkout starts fresh on the next
launch without asking; `--new` remains the escape for forcing a second instance of the
SAME code.

Deliberately NOT adopted from the Jupyter model it parallels: **no auth token** (this
server executes nothing and serves read-only inside one root; the Host-header
rebinding guard and the preflight-forcing POST header cover the actual threat model),
and **no HTTP shutdown route** (`stop`'s identity-probed signal can never kill a
port-squatter, which is stronger than an authenticated endpoint).

## One root per instance

An instance serves ONE directory: the one it is launched from. There is no flag
for it — the cwd IS the served directory, so the caller chooses what to serve by
choosing where to run (dev hands the choice down the same way, as the spawned
backend's cwd). Requests never name a directory: there is no `?dir=` param, and
`?file=` is always resolved inside the served root. Anything resolving outside that
root is refused, unconditionally. Serving a second directory means launching again
from it (reuse-or-start makes it idempotent); `python server/main.py list`
reports which root each running instance holds (and `stop --port <n>` ends one).

The root is resolved and checked once, in `LocalAssetBackend`'s constructor
(`server/backend.py`), so every later request is measured against a directory
already known to exist.

## Interface

`server/backend.py` holds `LocalAssetBackend` (root containment, catalog
absolutization, the guarded path resolver); `server/scanner.py` holds the catalog
scan; `server/cadgen_ops.py` holds the cadgen delegation:

```python
backend.resolve_root()                        # the served root, resolved once
backend.read_catalog()                        # scan -> schema v4 entries
backend.asset_path_for_file_ref(file_ref)     # guarded path for bytes we will send
backend.catalog_entry_for_file_ref(catalog, file_ref)
ops.artifact_status(file_ref)                 # freshness verdict + advisory progress
ops.build_artifact(file_ref, force=False)     # compiles a raw STEP via cadgen; else a CLI hint
```

`read_catalog()` scans the served root and returns schema v4 entries whose `file`
values are absolute paths plus `rootRelativeFile` values for URL navigation. Nothing
is written to `catalog.json` or any hidden catalog cache.

`asset_path_for_file_ref` answers "may the server send this file's contents", so on
top of the root and hidden-path rules it applies the served-asset extension filter,
which excludes a model script. It throws on anything outside the root.

The outside-the-root half of that is `require_contained(root, candidate)`, and it
is ONE function on purpose: the artifact routes call it too, because "refused
unconditionally" has to include the route that COMPILES. Without it,
`GET /__cad/asset?file=<outside>.step` was correctly 403 while
`POST /__cad/artifact?file=<outside>.step` compiled that file into the shared
store — after which `/__cad/store` served its geometry component by component,
a file outside the served root readable in full. Absolute refs are not the
problem and are not refused as a class (the catalog absolutizes every entry's
`file` and the client sends exactly that back); an absolute ref that LANDS
outside is.

## Artifact status (file reads only), and where builds live

Artifact STATUS has exactly one authority: `server/artifact_status.py`, pure file
reads in this process — package existence, schema version, payload files, the
no-bake gate, and the imported-file digest gate. Generated-vs-imported is decided
by the source sidecar's EXISTENCE (`<package>/source.json`, written only by
generation): the descriptor (`assembly.json`) is a pure function of the STEP
bytes and carries no provenance; everything source-derived — source path/hashes,
the pose block, assembly mates — rides the sidecar. Generated outputs are
DETACHED from their source code: the viewer never treats "the generator changed
since this artifact was built" as a reason to rebuild, and it does not rebuild
generated entries at all — a generated model with no artifact reports an error
that names the build (`python <model>.py`), not a build offer.

A CLI build in flight is shown ADVISORILY: the build's status record
(`.<name>.generation.progress.json`, written by cadgen's coordination layer) is
read for a `generating` badge with progress when it is fresh and non-terminal.
The viewer takes no action on that state — it never contends for the generation
lock — so the kernel-lock rules in `cadgen/coordination/lock.py` are not being
re-inferred here; a killed build's badge simply ages out within seconds.

This authority mirrors cadgen's store layout — the cache schema version, the
package and record directories, the path-key derivation — in `server/store_paths.py`,
a deliberate duplicate so that merely VIEWING never requires cadgen. The duplicate is
paid for by `tests_server/test_store_paths.py`, which asks both implementations the
same questions over a matrix of environment states and requires identical answers. It
skips where cadgen is absent (here, by design); set `VIEWER_REQUIRE_CADGEN_PARITY=1`
and an absent cadgen becomes a failure instead, which is how the workbench that
develops both sides runs it.

`/__cad/server` reports `stepArtifactGenerationAvailable: false`, always: the
capability does not exist in the viewer by design. `stepImportAvailable` reports
whether a runnable cadgen was found (see the import section below); viewing is
unaffected either way.

## STEP import (via cadgen)

A raw `.step`/`.stp` with no render package (or a stale one — the file changed after
import) is importable right here: the server calls cadgen's compile entry point —
the single import producer — inside a private worker process it owns, which parses
the STEP natively and writes the standard package. Results, errors and PROGRESS
come back as framed data on a dedicated channel rather than being scraped from
stdout and exit codes.

cadgen is a SOFT dependency of the interpreter running the server, and that
interpreter is the only place it is looked for: no `CADGEN_PYTHON`, no `cadgen` on
PATH, no `<served-root>/.venv`. Dropping that ladder also closed a real hole — the
served directory could supply the interpreter that got executed, so opening an
untrusted folder shipping a `.venv` was an execution vector the moment an import
ran. Do not reintroduce interpreter discovery in any form. Without an importable
cadgen, status and build answer with one actionable message and viewing is
untouched; `/__cad/server` reports it as `stepImportAvailable`.

The worker is a separate process on purpose: OCCT segfaults are a real failure mode
in this repo, and a kernel crash must cost one worker rather than the viewer. A
crash surfaces as the ordinary `{ok:false, state:"error"}` the client already
renders, the write lock releases at process death (it is `flock`), and the next
request lazily spawns a replacement.

The child is spawned with `--lock-timeout 5` and cwd set to the STEP's own
directory. A `contended` answer (a peer process holds the package lock) maps to
`generating`, which the client already treats as "attach to the running build".
A bare `.step` with no package is simply importable, whatever produced it —
STEP files carry no cadgen metadata of any kind, so there is nothing to read
from the file beyond its geometry.

Progress needs no protocol of its own: `cadgen step compile` writes the standard build
progress record beside the package (phase fields flattened, the exact shape the
client badge renders), and the status route serves it through the same reader
used for CLI builds (`build_progress_snapshot` in `build_progress.py`). One reader,
every producer.

## Routes

- `GET /__cad/server`
- `GET /__cad/catalog`
- `GET /__cad/asset?file=...`
- `GET /__cad/artifact?file=...` (status)
- `POST /__cad/artifact?file=...` (build; `&force=1` to rebuild)
- `GET /__tess_cache/<key>.tess`, `POST /__tess_cache/<key>.tess`,
  `POST /__tess_cache/batch` — the shared component-tessellation cache
  (`<cache root>/meshes`, the same store the export CLI and the snapshot host
  use; the entry codec, the key scheme — `<cid>-t<tessellator-version>-l<chord>-a<angle>` —
  and the TESB batch format live in cadgen-js `lib/surf/tessellationCache.js`). The client registers a provider at
  bootstrap, so component loads and viewport-LOD level re-tessellations are
  cache hits whenever ANY consumer — a snapshot, an export, a previous viewer
  session — tessellated the component before, and misses write back. Entries
  are opaque bytes living OUTSIDE every served root, so names are strictly
  validated (`server/tess_cache.py`; its store I/O is an independent Python
  implementation of the same layout as cadgen-js's `tessellationCacheFs`, kept
  honest by an equality test against cadgen, because the bundled skill runtime
  ships no cadgen-js tree). `CADGEN_MESH_CACHE=0` disables both directions,
  and every cache failure degrades to plain in-page tessellation.

### Storage tiers, in one rule

`~/.cache/cadgen` (or `$CADGEN_CACHE_DIR`, or the platform cache dir —
`$XDG_CACHE_HOME`/`%LOCALAPPDATA%`; one resolution rule in cadgen's
`_internal/cache_paths.py`, mirrored by `cadgen_cache_root_dir` in `server/store_paths.py`
and equality-tested against it) holds everything CONTENT-ADDRESSED and DISPOSABLE:
the component store, the kernel-op memo, and this mesh cache. Deleting any of
it costs a rebuild, never correctness. The model's own folder holds everything
meaningful: the artifact and its store package
(hardlinked into the store where possible, so the heavy bytes exist once).
Version bumps orphan whole cache generations by design; `cadgen cache info` /
`cadgen cache gc` are the only sweepers — nothing collects garbage
automatically.

`asset` streams asset bytes for rendering, never for saving — there is no download
route and no content-disposition header anywhere. It serves OUTPUTS only — the
artifacts the viewer may have to regenerate — and never source code: a model script
(`.py`) is not in the served-asset extension set, so it is not reachable through any
route.

No route hands a path to a desktop program. The server answers with bytes and JSON;
it never spawns a file manager or any other GUI application on the user's machine,
and a route that did would be a new class of thing for this backend to be.

**Every POST must send `x-cadgen-viewer: 1`.** The value carries no meaning — a custom
header is what forces a browser to preflight a cross-origin request, and the backend
answers no CORS, so the preflight fails and a hostile page can never reach a route
that builds (and therefore executes a generator). A POST without it gets 403. GETs are
unaffected. A second gate refuses any Host header naming a non-local name
(DNS-rebinding defense). See the trust-model comment in `server/http_app.py`.

**The viewer never touches the network.** Every byte it serves or reads is local;
the import spawns a local process, never a fetch.
