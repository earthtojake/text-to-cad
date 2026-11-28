# hosts/node (prototype)

The view core under Node: `viewcore.mjs` loads the module with the browser host's own loader and WASI shim, and
`serve.mjs` is a job server that answers the engine's pool jobs from it, in one long-lived process of a few tens of
megabytes. Nothing in cad starts it yet.

    node serve.mjs [VIEWCORE_WASM]        # default: ../../dist/viewcore.wasm (scripts/core.sh)

It needs Node 22 or later (the module uses standard WebAssembly exceptions). One process runs one job at a time, in
the order asked; several run side by side and share nothing. It ends when its input closes, or after a `close` job.

## Frames

Both ways, on the standard streams:

| Bytes | What |
|---|---|
| 8 | `N`, the length of the rest of the frame, unsigned, big-endian |
| 4 | `H`, the header's length, unsigned, big-endian |
| `H` | the header: one JSON object, UTF-8 |
| `N - 4 - H` | the payloads, end to end; the header's `payloads` lists their lengths in order |

A request's header is `{"id": ..., "job": NAME, ..., "payloads": [...]}`. Its answer carries the same `id` and either
`{"ok": true, ..., "payloads": [...]}` or `{"ok": false, "job": NAME, "error": TEXT}`. What the kernel refuses (bytes
that are no shape, an ordinal the part has not, a file that is no `.xbf`), a job this does not know and a frame it
cannot read are each an answer: the server goes on with the next frame. A frame longer than 2 GiB is passed over
as it comes and answered so.

## Jobs

Each answers what the engine's own job answers, in the engine's bytes: JSON is spelled as
`json.dumps(value, separators=(",", ":"))` spells it, a mesh is the XBM2 buffer of `Mesh.to_bytes()`.

| Job | Header, payloads | Answer | The engine's (`cad.engine`) |
|---|---|---|---|
| `about` | | `{abi, occt, memoryBytes}` | |
| `mesh` | `{tolerance?, angle?}`, a part's shape bytes | `{unmeshed: {ordinal: text}, seconds}`, the XBM2 buffer | `serve._timed`: `mesh_shape(data, tolerance=, angle=)`, its `to_bytes()` and `unmeshed` |
| `table` | `{key?, unmeshed: [ordinals], measure?}`, shape bytes | the table's JSON; then the measure's JSON where asked | `serve._table`: `Topology(data).elements(unmeshed)`, `.measured()` |
| `measured` | `{keys?}`, shape bytes of each part | each part's measure JSON, in order | `serve._measured` |
| `fact` | `{key?, method, args}`, shape bytes | the JSON | `serve._topology_fact`: `face`, `edge`, `vertex` (`args: [ordinal]`), `groups` (`[]`), `elements` (`[[ordinals]]`), `measured` (`[]`) |
| `read_xbf` | `{path}` | `{path, version: [mtime_ns as text, size], parts: [{key, name}...]}`, the structure's JSON, then each part's shape bytes in the parts' order | `serve._read_document` |
| `export` | `{path, format}` (`step`, `stl`, `threemf`, `glb`) | the file's bytes | `export.translate(path, kind, ...)` at the engine's own tessellation |
| `close` | | `{}`, and the process ends | |

- **A part's shape bytes** are `mesh.shape_bytes(shape, read=True)`: what `read_xbf` answers for each part, and what
  the engine keeps by the part's geometry key.
- **`key`** names the part for the jobs that follow: its topology is kept (the last 32 parts), as an engine pool
  process keeps it, so a table, its measure and a pick's facts read the shape once. Without it the part is opened
  for the job alone.
- **`read_xbf`'s structure** is the core's (`vc_structure`): the engine's `Loaded.structure()` once `path` and
  `version` (`"<mtime_ns>-<size>"`) are put in and `tessellation` and `closure`, which the server adds itself, are
  taken out. Colours are lists, as JSON has them, where the engine's own holds tuples. The file stays open for an
  `export` of it as it stood (the last 2 files): nothing is read twice.
- **An export's own tolerance** is the `mesh` job's (`tolerance` in millimetres, `angle` in degrees: the finer of
  each and the part's own, as `mesh_shape` takes them). The `export` job writes at the engine's tessellation only.
- **A face's fact** is a pick's: it says its checker's verdict. A table's row says it only for the faces named
  unmeshed.

`../../tools/pool_parity.py` holds every job against the engine's own code, part by part.
