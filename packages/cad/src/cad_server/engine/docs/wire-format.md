# Wire format

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

**The HTTP API.** Everything a page calls is under `/api/v1` (`cad_server/viewer/http_app.py`, its
kinds `viewer/kinds.py`); the pages are at the root -- `/` the home, `/<id>` a document's page,
`/app` the CAD app's module a card's shell imports. The version is in the path: within v1 a route
or a key is only ever added, and a removal or a rename is a v2. Every answer is JSON but a file's
bytes; every refusal is `{"error", "hint"}` -- what is wrong and what to do -- with its status: 400
for a body or query the route cannot read, 404
for an unknown route, kind or id (a document's names its `state` where the engine says one), 405
naming the methods the route takes (`Allow`), 413 for a body over its route's limit, 409 where
the server's state refuses a change: a telemetry answer to a server that keeps no usage stats
(`settings`), an export of a session
that restarted or of a source that changed since the page showed it, and 410 for an export's file
already fetched or past its window. Every request that changes something (POST, PUT, PATCH, DELETE)
carries `x-cad-viewer`, the gate a cross-site form cannot pass (403 without it). The families:

| Route | What it answers |
| --- | --- |
| `GET /api/v1/server` | who this engine is (`app`, `release`, `identityToken`, `platform`, `user`, `home`, `start`, `pick`, `port`, `pid`), `instance` (a random token of this start of it: a page that sees another reloads), and `kinds` (`reads`, and each kind's `exports`) |
| `GET\|PUT /api/v1/settings` | `{"language": {"locale"}, "telemetry": {"share", "reason", "policy"}, "whats_new": {"seen", "release"}}` (`telemetry` null where the server keeps none, `saved` beside it after a change; `whats_new` the releases whose What's new the person has seen), the person's, one for every view; PUT takes the same shape, or a part of it (the read-only `reason`, `policy` and `release` ignored), and answers the whole |
| `GET /api/v1/look`, `/api/v1/look/environment` | the regular modes' look, and its Radiance image |
| `GET /api/v1/documents`, `/api/v1/documents/<kind>` | Recents (of one kind): `{"documents": [row]}`, each row its document's `id`, `kind`, `api` and its record's kind (`record`); `?kind=`, `?q=`, `?limit=`; `?path=` one file's envelope, known by its id from then on |
| `POST /api/v1/documents` | a file opened (`{"path"}`) or a held model served (`{"id"}`): `201 {"id", "kind", "api"}`, or `202` (and `Retry-After`) while the engine reads it |
| `PATCH /api/v1/documents` | a change to Recents (`{"action", "path", "png"?}`), answered with Recents |
| `GET\|DELETE /api/v1/documents/<id>` | the envelope -- `id`, `kind`, `name`, `version`, `state`, `source` (a model's script or a file's path, with `present`: whether that file is there now), `producers`, `api`, `exports`, the row (`entry`) and its digest (`revision`), `held` for a document the engine serves -- or the document forgotten (204) |
| `GET /api/v1/documents/<id>/version`, `.../thumbnail` | its version, waited on (**Progress**); its picture, the PNG the page kept, as it kept it (a `?v=` the page adds is ignored: it keeps an older picture out of a cache) |
| `POST /api/v1/documents/<id>/exports` | an export of it, its job (202); `GET /api/v1/exports[/<job>[/file]]` the session's epoch, a job, its file |
| `/api/v1/documents/<kind>/<id>/...` | a kind's reads (below); the id under another kind is a 404 naming its own |
| `/api/v1/local/...` | a local engine's: `folder?path=&q=`, `files?path=` (a CAD file's bytes), `prompt-files[/<name>]`, `reveal`, `clipboard`, `pick`, `activity` |
| `GET /api/v1/local/link` | `{"link", "expires"}`: the link (`<expires>.<mac>`, `expires` in Unix seconds), the same text every call until the token is rotated, that the page keeps in its address, so a copied address opens it in another browser on this machine; it also answers the CAD app, through a card's tunnel, for its Copy link |
| `GET /api/v1/local/open-in?id=<id>` | Open in: `{"targets": [{"target", "kind", "name", "present", "apps": [{"id", "name", "refuses"}], "default"}], "fileManager"}` -- a model's `source` (its script, kind `script`) then one `export:<kind>` for each kind of file its last build wrote, a file's `source` alone; each with whether it is there now and the apps found on this computer that take its kind (`_internal/apps.py`: looked for in the background, never on a request). A KiCad's `name` says its version (`KiCad 9.0.6`, `KiCad 10.99 nightly`), and `refuses: "newer"` marks one that cannot read this file's format, listed rather than hidden; `default: false` on a `.kicad_*` file, whose operating-system handler is never started; `fileManager` `finder`, `explorer` or `files`; 404 for an unknown id |
| `POST /api/v1/local/open` | `{"id", "target", "app"}`: one of those targets in one of its apps, or `"default"` (the system's own handler), started detached and never through a shell (a KiCad by its board or schematic editor, as the file's extension says; Blender, which opens only a `.blend` from its command line, with the package's import script, `--python`, and the file as the one argument after `--`): 204; 400 for a target the document lacks, an app not found for its kind, a KiCad that `refuses` the file or `"default"` on a `.kicad_*` file, 404 for a document or a file not there. Only the server's own paths and apps are opened |

A kind's routes: `model`, `xbf` and `step` -- `structure`, `parts/<key>` (and its
`faces|edges|vertices/<ordinal>`, `groups`, `volume`), `measure`, `kinematics`, `POST pose`,
`POST mesh`, a model's `POST parameters` (**Parameters**) and a file's `source`; `dxf` -- `drawing`, `source`; `kicad_pcb` -- `plot` (the
board's geometry per layer and its index, read from the file on each request: `viewer/plots.py`),
`source`; `kicad_sch` -- `plot` (every sheet of the hierarchy a page, and the schematic's index;
`?sheet=<path>` that sheet's page alone, `index=0` without the index; the hierarchy parsed once per
revision of its files, `viewer/plots.py`'s `SchematicAnswers`), `source`; `urdf`, `srdf` --
`structure`, `parts/<digest>`, `source`; `stl`, `glb`, `3mf` -- `source`. Each engine read is
`serve.py`'s own, asked in process (`viewer/engine_app.py`): `structure` is its `/api/doc/<id>`,
`parts/<key>` its `/part/<key>`, `measure` its `/volumes` -- the vocabulary the door's `read` speaks
too (`cad <type> inspect`), never served over the engine's HTTP listener. The look is `serve.py`'s at the
API's own paths (`/api/v1/look`, `/api/v1/look/environment`), the ones its record names, which the
daemon's listener serves as they are.

`GET /api/v1/documents/<kind>/<id>/structure` returns the structure as JSON: prototypes (key, name,
colour, `faceNames`, `edgeNames`, `vertexNames`, `faceColors` by ordinal, `material` and
`faceMaterials` by ordinal -- each every field of the `Material`, named in camelCase
(`youngModulus`, `transmissionColor`, ...), its colour the base colour it is drawn in, SI
-- `untextured` where a material carries texture maps the renderers leave out (**Materials**), and
once meshed `unmeshed`/`unmeshedCheck`), instances (prototype, path, a 4x4 world matrix,
colour), the tree, the document's version, and for an assembly with joints `kinematics` (also its
own route, `.../kinematics`): the
links (name, the instances each moves, its frame as built), the pairs (label, type, the two
links, the two frames as 4x4 matrices in their links' frames, limits and units per value), the
ground link, `asBuilt` and `configurations` (name → joint → value: a number, or a list for a
cylindrical or spherical pair), `couplings` (name → `{range, terms}`), `motions` (name →
`{duration, ease, keys}`, each key `{t, configuration}` or `{t, values}`), `loop` (the pairs
closing a loop, or null) and the build's `warnings`. A page poses the instances from it: each link's
placement at the values over its placement as built, applied to its instances.
`POST .../pose` (`{"pose": NAME | {joint: value}}`) answers the id of the
document served at that pose, where it is read (`api`), and its `kinematics.pose` the values it stands at.
The structure's `parameters` is the list the document records, always there (`[]` for none), each
parameter served with `writable`, `reason` and `source` (**Parameters**); a model's own `POST
.../parameters` sets them.
`GET /api/v1/look` is the look the regular display modes are drawn in (**The viewer and the
snapshot**), the same for every document; `GET /api/v1/look/environment` is its environment, the
Radiance image `render/studio.hdr`.
`GET /api/v1/documents/<id>/version?after=V&wait=S` answers as soon as the version is not
`V` (or after `S` seconds, at most 60): the page waits on it, so a model's new build,
or a file's new bytes, reaches it at once.

`GET .../parts/<key>` returns one part's buffer. A client reads it
with typed-array views, without parsing. It is sent immutable, so a page asks
for it with the structure's `tessellation` (`?tessellation=0.25-28.5`, the
mesh constants by name) and never draws a buffer an engine made at others. The header grew from 64 to 80 bytes in
`XBM2` (the vertex table's count and offset did not fit). The 80-byte
little-endian header is:

| Bytes | Field |
| --- | --- |
| 0-3 | magic `XBM2` |
| 4-7 | format version (2) |
| 8-31 | counts: nodes, indices, faces, edges, edge points, vertices (u32 each) |
| 32-59 | byte offsets of the seven arrays below (u32 each) |
| 60-67 | linear and angular deflection (f32 each) |
| 68-79 | reserved |

Then the arrays, each 4-byte aligned: positions `f32[N*3]`, surface normals
`f32[N*3]`, triangle indices `u32[I]`, the face table `u32[F*3]` (face ordinal,
first index, index count; an unmeshed face's count is 0), the edge table
`u32[E*4]` (edge ordinal, first point, point count, class), the edge polylines
`f32[P*3]`, and the vertex table `f32[X*4]` (vertex ordinal, x, y, z) of every
vertex of the part. Ordinals are the part's `TopExp.MapShapes` ordinals, the
same ones its element names use. Selecting a face reads a range of the index
buffer, an edge a range of the polyline buffer, a vertex a row of the vertex
table.

`POST .../mesh?mode=inline|processes[&drop=1]` meshes every part not
held yet (with `drop=1`, every part again), in parallel, and returns the time it
took, the bytes, the triangles and the unmeshed faces.
